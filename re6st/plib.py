import os, subprocess, logging
import utils

verbose = 0


def openvpn(hello_interval, *args, **kw):
    args = ['openvpn',
        '--dev-type', 'tap',
        '--persist-tun',
        '--persist-key',
        '--script-security', '2',
        '--user', 'nobody',
        '--ping-exit', str(4 * hello_interval),
        '--group', 'nogroup',
        ] + list(args)
    logging.trace('%s' % (args,))
    return subprocess.Popen(args, **kw)


def server(server_ip, ip_length, max_clients, dh_path, pipe_fd, port, proto, hello_interval, *args, **kw):
    logging.debug('Starting server...')
    return openvpn(hello_interval,
        '--tls-server',
        '--mode', 'server',
        '--up', 'ovpn-server %s/%u' % (server_ip, 64),
        '--client-connect', 'ovpn-server ' + str(pipe_fd),
        '--client-disconnect', 'ovpn-server ' + str(pipe_fd),
        '--dh', dh_path,
        '--max-clients', str(max_clients),
        '--port', str(port),
        '--proto', proto,
        *args, **kw)


def client(server_address, pipe_fd, hello_interval, *args, **kw):
    logging.debug('Starting client...')
    remote = ['--nobind',
              '--client',
              '--up', 'ovpn-client',
              '--route-up', 'ovpn-client ' + str(pipe_fd)]
    try:
        for ip, port, proto in utils.address_list(server_address):
            remote += '--remote', ip, port, proto
    except ValueError, e:
        logging.warning('Error "%s" in unpacking address %s for openvpn client'
                % (e, server_address,))
    remote += args
    return openvpn(hello_interval, *remote, **kw)


def router(network, internal_ip, interface_list,
           wireless, hello_interval, state_path, **kw):
    logging.info('Starting babel...')
    args = ['babeld',
            '-C', 'redistribute local ip %s' % (internal_ip),
            '-C', 'redistribute local deny',
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
    if wireless:
        args.append('-w')
    args = args + interface_list
    logging.trace('%s' % args)
    return subprocess.Popen(args, **kw)
