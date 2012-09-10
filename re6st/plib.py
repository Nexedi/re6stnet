import logging, errno, os, subprocess
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
        #'--user', 'nobody', '--group', 'nogroup',
        ] + list(args)
    if ovpn_log:
        args += '--log-append', os.path.join(ovpn_log, '%s.log' % iface),
    if not encrypt:
        args += '--cipher', 'none'
    logging.debug('%r', args)
    return subprocess.Popen(args, **kw)


def server(iface, my_ip, max_clients, dh_path, pipe_fd, port, proto, encrypt, *args, **kw):
    client_script = '%s %s' % (ovpn_server, pipe_fd)
    if pipe_fd is not None:
        args = ('--client-disconnect', client_script) + args
    return openvpn(iface, encrypt,
        '--tls-server',
        '--mode', 'server',
        '--up', '%s %s' % (ovpn_server, my_ip),
        '--client-connect', client_script,
        '--dh', dh_path,
        '--max-clients', str(max_clients),
        '--port', str(port),
        '--proto', 'tcp-server' if proto == 'tcp' else proto,
        *args, **kw)


def client(iface, server_address, encrypt, *args, **kw):
    remote = ['--nobind', '--client']
    try:
        for ip, port, proto in utils.address_list(server_address):
            remote += '--remote', ip, port, \
                'tcp-client' if proto == 'tcp' else proto
    except ValueError, e:
        logging.warning("Failed to parse node address %r (%s)",
                        server_address, e)
    remote += args
    return openvpn(iface, encrypt, *remote, **kw)


def router(network, subnet, subnet_size, hello_interval, log_path, state_path,
           pidfile, tunnel_interfaces, *args, **kw):
    cmd = ['babeld',
            '-C', 'redistribute local ip %s/%s le %s' % (subnet, subnet_size, subnet_size),
            '-C', 'redistribute local deny',
            '-C', 'redistribute ip %s/%s le %s' % (subnet, subnet_size, subnet_size),
            '-C', 'redistribute deny',
            '-C', 'out local ip %s/%s le %s' % (subnet, subnet_size, subnet_size),
            '-C', 'out local deny',
            '-C', 'in ip %s/%u' % (utils.ipFromBin(network), len(network)),
                  # Route only addresse in the 'local' network,
                  # or other entire networks
                  #'-C', 'in ip %s' % (config.internal_ip),
                  #'-C', 'in ip ::/0 le %s' % network_mask,
            '-C', 'in deny',
            '-h', str(hello_interval),
            '-H', str(hello_interval),
            '-L', log_path,
            '-S', state_path,
            '-I', pidfile,
            '-s']
    for iface in tunnel_interfaces:
        cmd += '-C', 'interface %s rxcost 512' % iface
    cmd += args
    # WKRD: babeld fails to start if pidfile already exists
    try:
        os.remove(pidfile)
    except OSError, e:
        if e.errno != errno.ENOENT:
            raise
    logging.info('%r', cmd)
    return subprocess.Popen(cmd, **kw)
