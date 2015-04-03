import logging, errno, os
from . import utils

here = os.path.realpath(os.path.dirname(__file__))
ovpn_server = os.path.join(here, 'ovpn-server')
ovpn_client = os.path.join(here, 'ovpn-client')
ovpn_log = None

def openvpn(iface, encrypt, *args, **kw):
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
        args += '--cipher', 'none'
    logging.debug('%r', args)
    return utils.Popen(args, **kw)

ovpn_link_mtu_dict = {'udp': 1481, 'udp6': 1450}

def server(iface, max_clients, dh_path, fd, port, proto, encrypt, *args, **kw):
    client_script = '%s %s' % (ovpn_server, fd)
    try:
        args = ('--link-mtu', str(ovpn_link_mtu_dict[proto]),
                # mtu-disc ignored for udp6 due to a bug in OpenVPN
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
        *args, **kw)


def client(iface, address_list, encrypt, *args, **kw):
    remote = ['--nobind', '--client']
    # XXX: We'd like to pass <connection> sections at command-line.
    link_mtu = set()
    for ip, port, proto in address_list:
        remote += '--remote', ip, port, proto
        link_mtu.add(ovpn_link_mtu_dict.get(proto))
    link_mtu, = link_mtu
    if link_mtu:
        remote += '--link-mtu', str(link_mtu), '--mtu-disc', 'yes'
    remote += args
    return openvpn(iface, encrypt, *remote, **kw)


def router(subnet, hello_interval, table, log_path, state_path, pidfile,
           control_socket, default, *args, **kw):
    s = utils.ipFromBin(subnet)
    n = len(subnet)
    cmd = ['babeld',
            '-h', str(hello_interval),
            '-H', str(hello_interval),
            '-L', log_path,
            '-S', state_path,
            '-I', pidfile,
            '-s',
            '-C', 'default ' + default,
            '-C', 'redistribute local deny',
            '-C', 'redistribute ip %s/%u eq %u' % (s, n, n),
            '-C', 'redistribute deny']
    if table:
        cmd += '-t%u' % table, '-T%u' % table
    else:
        cmd[-2:-2] = '-C', 'redistribute ip ::/0 eq 0'
    if control_socket:
        cmd += '-R', '%s' % control_socket
    cmd += args
    # WKRD: babeld fails to start if pidfile already exists
    try:
        os.remove(pidfile)
    except OSError, e:
        if e.errno != errno.ENOENT:
            raise
    logging.info('%r', cmd)
    return utils.Popen(cmd, **kw)
