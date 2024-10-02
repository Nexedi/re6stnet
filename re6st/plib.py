import binascii
import logging, errno, os
from typing import Optional
from . import utils

here = os.path.realpath(os.path.dirname(__file__))
ovpn_server = os.path.join(here, 'ovpn-server')
ovpn_client = os.path.join(here, 'ovpn-client')
ovpn_log: Optional[str] = None

def openvpn(iface: str, encrypt, *args, **kw) -> utils.Popen:
    args = ['openvpn',
        '--dev-type', 'tap',
        '--dev', iface,
        '--persist-tun',
        '--persist-key',
        '--script-security', '2',
        '--up', ovpn_client,
        #'--user', 'nobody', '--group', 'nogroup',
        ] + list(args)
    if ovpn_log:
        args += '--log-append', os.path.join(ovpn_log, '%s.log' % iface),
    if not encrypt:
        # TODO: --ncp-disable was deprecated in OpenVPN 2.5 and removed in 2.6
        #       and is no longer necessary in those versions.
        args += '--cipher', 'none', '--ncp-disable'
    logging.debug('%r', args)
    return utils.Popen(args, **kw)

ovpn_link_mtu_dict = {'udp4': 1432, 'udp6': 1450}

def server(iface: str, max_clients: int, dh_path: str, fd: int,
           port: int, proto: str, encrypt: bool, *args, **kw) -> utils.Popen:
    if proto == 'udp':
        proto = 'udp4'
    client_script = '%s %s' % (ovpn_server, fd)
    try:
        args = ('--link-mtu', str(ovpn_link_mtu_dict[proto] + 93),
                '--mtu-disc', 'yes') + args
    except KeyError:
        proto += '-server'
    return openvpn(iface, encrypt,
        '--tls-server',
        '--mode', 'server',
        '--client-connect', client_script,
        '--client-disconnect', client_script,
        '--dh', dh_path,
        '--max-clients', str(max_clients),
        '--port', str(port),
        '--proto', proto,
        *args, pass_fds=[fd], **kw)


def client(iface: str, address_list: list[tuple[str, int, str]],
           encrypt: bool, *args, **kw) -> utils.Popen:
    remote = ['--nobind', '--client']
    # XXX: We'd like to pass <connection> sections at command-line.
    link_mtu = set()
    for ip, port, proto in address_list:
        if proto == 'udp':
            proto = 'udp4'
        remote += '--remote', ip, port, proto
        link_mtu.add(ovpn_link_mtu_dict.get(proto))
    link_mtu, = link_mtu
    if link_mtu:
        remote += '--link-mtu', str(link_mtu), '--mtu-disc', 'yes'
    remote += args
    return openvpn(iface, encrypt, *remote, **kw)


def router(ip: tuple[str, int], ip4, rt6: tuple[str, bool, bool],
           hello_interval: int, log_path: str, state_path: str, pidfile: str,
           control_socket: str, default: str,
           hmac: tuple[bytes | None, bytes | None], *args, **kw) -> utils.Popen:
    network, gateway, has_ipv6_subtrees = rt6
    network_mask = int(network[network.index('/')+1:])
    ip, n = ip
    hmac_sign, hmac_accept = hmac
    if ip4:
        ip4, n4 = ip4
    cmd = ['babeld',
            '-h', str(hello_interval),
            '-H', str(hello_interval),
            '-L', log_path,
            '-S', state_path,
            '-I', pidfile,
            '-s',
            '-C', 'redistribute local deny',
            '-C', 'redistribute ip %s/%s eq %s' % (ip, n, n)]
    if hmac_sign:
        def key(cmd: list[str], id: str, value: bytes):
            cmd += '-C', ('key type blake2s128 id %s value %s' %
                          (id, binascii.hexlify(value).decode()))
        key(cmd, 'sign', hmac_sign)
        default += ' key sign'
        if hmac_accept is not None:
            if hmac_accept:
                key(cmd, 'accept', hmac_accept)
            else:
                default += ' accept-bad-signatures true'
    cmd += '-C', 'default ' + default
    if ip4:
        cmd += '-C', 'redistribute ip %s/%s eq %s' % (ip4, n4, n4)
    if gateway:
        cmd += '-C', 'redistribute ip ::/0 eq 0 src-prefix ' + network
        if not has_ipv6_subtrees:
            cmd += (
                '-C', 'in ip %s ge %s' % (network, network_mask),
                '-C', 'in ip ::/0 deny',
            )
    elif has_ipv6_subtrees:
        # For backward compatibility, if the default route comes from old
        # version (without source-prefix).
        cmd += (
            '-C', 'install ip ::/0 eq 0 src-ip ::/0 src-eq 0 src-prefix ' + network,
        )
    else:
        # We patch babeld:
        # - ipv6-subtrees is always true by default
        # - if false, source prefix is cleared when the route is installed
        cmd += (
            '-C', 'ipv6-subtrees false',
            # Accept default route from our network.
            '-C', 'in ip ::/0 eq 0 src-ip %s src-eq %s' % (network, network_mask),
            # Ignore default route from other networks. For backward
            # compatibility we accept default routes from old version
            # (without source-prefix).
            '-C', 'in ip ::/0 eq 0 src-ip ::/0 src-ge 1 deny',
            # Tell neighbours not to route to the internet via us,
            # because we could be a black hole in case of misconfiguration.
            '-C', 'out ip ::/0 eq 0 deny',
        )
    cmd += ('-C', 'redistribute deny',
            '-C', 'install pref-src ' + ip)
    if ip4:
        cmd += '-C', 'install pref-src ' + ip4
    if control_socket:
        cmd += '-X', '%s' % control_socket
    cmd += args
    # WKRD: babeld fails to start if pidfile already exists
    try:
        os.remove(pidfile)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
    logging.info('%r', cmd)
    return utils.Popen(cmd, **kw)
