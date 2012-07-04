import subprocess

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

def server(ip, *args):
    return openvpn(
        '--tls-server',
        '--keepalive', '10', '60',
        '--mode', 'server',
        '--duplicate-cn', # XXX : to be removed
        '--up', 'up-server ' + ip,
        '--dh', config.dh,
        *args)

def client(serverIp, *args):
    return openvpn(
        '--nobind',
        '--tls-client',
        '--remote', serverIp,
        '--up', 'up-client',
        *args)

