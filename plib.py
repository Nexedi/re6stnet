import os, subprocess
import utils

verbose = None

def openvpn(hello_interval, *args, **kw):
    args = ['openvpn',
        '--dev-type', 'tap',
        '--persist-tun',
        '--persist-key',
        '--script-security', '2',
        '--user', 'nobody',
        '--ping-exit', str(4 * hello_interval),
        '--group', 'nogroup',
        '--verb', str(verbose),
        ] + list(args)
    utils.log(str(args), 5)
    return subprocess.Popen(args, **kw)

# TODO : set iface up when creating a server/client
# ! check working directory before launching up script ?

def server(server_ip, network, max_clients, dh_path, pipe_fd, port, proto, hello_interval, *args, **kw):
    utils.log('Starting server', 3)
    return openvpn(hello_interval,
        '--tls-server',
        '--mode', 'server',
        '--up', 'ovpn-server %s/%u' % (server_ip, len(network)),
        '--client-connect', 'ovpn-server ' + str(pipe_fd),
        '--client-disconnect', 'ovpn-server ' + str(pipe_fd),
        '--dh', dh_path,
        '--max-clients', str(max_clients),
        '--port', str(port),
        '--proto', proto,
        *args, **kw)

def client(server_ip, pipe_fd, hello_interval, *args, **kw):
    utils.log('Starting client', 5)
    return openvpn(hello_interval,
        '--nobind',
        '--client',
        '--remote', server_ip,
        '--up', 'ovpn-client',
        '--route-up', 'ovpn-client ' + str(pipe_fd),
        *args, **kw)

def router(network, internal_ip, interface_list,
           wireless, hello_interval, **kw):
    utils.log('Starting babel', 3)
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
            '-s',
            ]
    #if utils.config.babel_state:
    #    args += '-S', utils.config.babel_state
    if wireless:
        args.append('-w')
    args = args + interface_list
    utils.log(str(args), 5)
    return subprocess.Popen(args, **kw)

