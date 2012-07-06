import subprocess
import os

def openvpn(*args, **kw):
    args = ['openvpn',
        '--dev-type', 'tap',
        '--persist-tun',
        '--persist-key',
        '--script-security', '2',
        '--user', 'nobody',
        '--ping', '1', 
            # I don't kown how Babel works, but if it test the
            # connection often, the ping directive might not be needed
            # if it test the connection very often, we could also decrease
            # ping-exit to 1 sec 
        '--ping-exit', '3', 
        '--group', 'nogroup',
        '--verb', str(config.verbose),
        ] + list(args) + config.openvpn_args
    if config.verbose >= 5:
        print repr(args)
    return subprocess.Popen(args, **kw)

# TODO : set iface up when creating a server/client
# ! check working directory before launching up script ?

def server(ip, pipe_fd, *args, **kw):
    return openvpn(
        '--tls-server',
        '--mode', 'server',
        '--duplicate-cn', # XXX : to be removed
        '--up', 'up-server ' + ip,
        '--client-connect', 'client-connect ' + str(pipe_fd),
        '--client-disconnect', 'client-disconnect ' + str(pipe_fd),
        '--dh', config.dh,
        *args, **kw)

def client(serverIp, *args, **kw):
    return openvpn(
        '--nobind',
        '--tls-client',
        '--remote', serverIp,
        '--up', 'up-client',
        *args, **kw)

