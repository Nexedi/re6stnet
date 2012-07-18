import os, subprocess
import utils

verbose = None

def openvpn(*args, **kw):
    args = ['openvpn',
        '--dev-type', 'tap',
        '--persist-tun',
        '--persist-key',
        '--script-security', '2',
        '--user', 'nobody',
        '--ping', '1',
        '--ping-exit', '3',
        '--group', 'nogroup',
        '--verb', str(verbose),
        ] + list(args)
    utils.log(str(args), 5)
    return subprocess.Popen(args, **kw)

# TODO : set iface up when creating a server/client
# ! check working directory before launching up script ?

def server(serverIp, network, max_clients, dh_path, pipe_fd, port, proto, *args, **kw):
    utils.log('Starting server', 3)
    return openvpn(
        '--tls-server',
        '--mode', 'server',
        '--up', 'ovpn-server %s/%u' % (serverIp, len(network)),
        '--client-connect', 'ovpn-server ' + str(pipe_fd),
        '--client-disconnect', 'ovpn-server ' + str(pipe_fd),
        '--dh', dh_path,
        '--max-clients', str(max_clients),
        '--port', str(port),
        '--proto', proto,
        *args, **kw)

def client(serverIp, pipe_fd, *args, **kw):
    utils.log('Starting client', 5)
    return openvpn(
        '--nobind',
        '--client',
        '--remote', serverIp,
        '--up', 'ovpn-client',
        '--route-up', 'ovpn-client ' + str(pipe_fd),
        *args, **kw)

def router(network, internal_ip, interface_list, **kw):
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
            '-s',
            ]
    #if utils.config.babel_state:
    #    args += '-S', utils.config.babel_state
    args = args + interface_list
    utils.log(str(args), 5)
    return subprocess.Popen(args, **kw)

