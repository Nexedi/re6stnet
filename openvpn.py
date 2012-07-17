import subprocess
import utils
import os

def openvpn(*args, **kw):
    args = ['openvpn',
        '--dev-type', 'tap',
        '--persist-tun',
        '--persist-key',
        '--script-security', '2',
        '--user', 'nobody',
            # I don't kown how Babel works, but if it test the
            # connection often, the ping directive might not be needed
            # if it test the connection very often, we could also decrease
            # ping-exit to 1 sec
            # '--ping', '1',
            # '--ping-exit', '3',
        '--group', 'nogroup',
        '--verb', str(utils.config.verbose),
        ] + list(args) + utils.config.openvpn_args
    if utils.config.verbose >= 5:
        print repr(args)
    return subprocess.Popen(args, **kw)

# TODO : set iface up when creating a server/client
# ! check working directory before launching up script ?

def server(ip, pipe_fd, *args, **kw):
    return openvpn(
        '--tls-server',
        '--mode', 'server',
        '--up', 'up-server %s/%u' % (ip, len(utils.config.vifibnet)),
        '--client-connect', 'client-connect ' + str(pipe_fd),
        '--client-disconnect', 'client-connect ' + str(pipe_fd),
        '--dh', utils.config.dh,
        '--max-clients', str(utils.config.max_clients),
        *args, **kw)

def client(serverIp, pipe_fd, *args, **kw):
    return openvpn(
        '--nobind',
        '--client',
        '--remote', serverIp,
        '--up', 'up-client',
        '--route-up', 'route-up ' + str(pipe_fd),
        *args, **kw)

