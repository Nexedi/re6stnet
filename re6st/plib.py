import errno
import os
import subprocess
import logging
import utils

here = os.path.realpath(os.path.dirname(__file__))
ovpn_server = os.path.join(here, 'ovpn-server')
ovpn_client = os.path.join(here, 'ovpn-client')


def openvpn(iface, hello_interval, encrypt, *args, **kw):
    args = ['openvpn',
        '--dev-type', 'tap',
        '--dev', iface,
        '--persist-tun',
        '--persist-key',
        '--script-security', '2',
        '--ping-exit', str(4 * hello_interval),
        #'--user', 'nobody', '--group', 'nogroup',
        ] + list(args)
    if not encrypt:
        args.extend(['--cipher', 'none'])
    logging.trace('%r', args)
    fd = os.open(os.path.join(log, '%s.log' % iface),
                 os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    try:
        return subprocess.Popen(args, stdout=fd, stderr=subprocess.STDOUT, **kw)
    finally:
        os.close(fd)


def server(iface, server_ip, ip_length, max_clients, dh_path, pipe_fd, port, proto, hello_interval, encrypt, *args, **kw):
    logging.debug('Starting server...')
    if server_ip:
        script_up = '%s %s/%u' % (ovpn_server, server_ip, 64)
    else:
        script_up = '%s none' % (ovpn_server)
    return openvpn(iface, hello_interval, encrypt,
        '--tls-server',
        '--mode', 'server',
        '--up', script_up,
        '--client-connect', ovpn_server + ' ' + str(pipe_fd),
        '--client-disconnect', ovpn_server + ' ' + str(pipe_fd),
        '--dh', dh_path,
        '--max-clients', str(max_clients),
        '--port', str(port),
        '--proto', 'tcp-server' if proto == 'tcp' else proto,
        *args, **kw)


def client(iface, server_address, pipe_fd, hello_interval, encrypt, *args, **kw):
    logging.debug('Starting client...')
    remote = ['--nobind',
              '--client',
              '--up', ovpn_client,
              '--route-up', ovpn_client + ' ' + str(pipe_fd)]
    try:
        for ip, port, proto in utils.address_list(server_address):
            remote += '--remote', ip, port, \
                'tcp-client' if proto == 'tcp' else proto
    except ValueError, e:
        logging.warning('Error "%s" in unpacking address %s for openvpn client'
                % (e, server_address,))
    remote += args
    return openvpn(iface, hello_interval, encrypt, *remote, **kw)


def router(network, subnet, subnet_size, interface_list,
           wireless, hello_interval, verbose, pidfile, state_path, **kw):
    logging.info('Starting babel...')
    args = ['babeld',
            '-C', 'redistribute local ip %s/%s le %s' % (subnet, subnet_size, subnet_size),
            '-C', 'redistribute local deny',
            '-C', 'redistribute ip %s/%s le %s' % (subnet, subnet_size, subnet_size),
            '-C', 'redistribute deny',
            '-C', 'out local ip %s/%s le %s' % (subnet, subnet_size, subnet_size),
            '-C', 'out local deny',
            # Route VIFIB ip adresses
            '-C', 'in ip %s::/%u' % (utils.ipFromBin(network), len(network)),
                  # Route only addresse in the 'local' network,
                  # or other entire networks
                  #'-C', 'in ip %s' % (config.internal_ip),
                  #'-C', 'in ip ::/0 le %s' % network_mask,
            # Don't route other addresses
            '-C', 'in deny',
            '-d', str(verbose),
            '-h', str(hello_interval),
            '-H', str(hello_interval),
            '-S', state_path,
            '-s',
            ]
    if pidfile:
        args += '-I', pidfile
    # WKRD: babeld fails to start if pidfile already exists
    else:
        pidfile = '/var/run/babeld.pid'
    try:
        os.remove(pidfile)
    except OSError, e:
        if e.errno != errno.ENOENT:
            raise
    if wireless:
        args.append('-w')
    args = args + interface_list
    logging.trace('%r', args)
    return subprocess.Popen(args, **kw)
