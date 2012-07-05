import subprocess
import os

def openvpn(*args, **kw):
    args = ['openvpn',
        '--dev-type', 'tap',
        '--persist-tun',
        '--persist-key',
        '--script-security', '2',
        '--user', 'nobody',
        '--group', 'nogroup',
        #'--verb', str(config.verbose),
        ] + list(args) + config.openvpn_args
    if config.verbose >= 5:
        print repr(args)
    return subprocess.Popen(args, **kw)

# TODO : set iface up when creating a server/client
# ! check working directory before launching up script ?

def server(ip, pipe_fd, *args, **kw):
    return openvpn(
        '--tls-server',
        '--keepalive', '10', '60',
        '--mode', 'server',
        '--duplicate-cn', # XXX : to be removed
        '--up', 'up-server ' + ip,
        '--client-connect', 'client-connect ' + str(pipe_fd),
        '--dh', config.dh,
        *args, **kw)

def client(serverIp, *args, **kw):
    return openvpn(
        '--nobind',
        '--tls-client',
        '--remote', serverIp,
        '--up', 'up-client',
        *args, **kw)

