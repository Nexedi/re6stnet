#!/usr/bin/env python
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
    utils.log('Starting server', 3)
    return openvpn(
        '--tls-server',
        '--mode', 'server',
        '--up', 'openvpn-up-server %s/%u' % (ip, len(utils.config.vifibnet)),
        '--client-connect', 'openvpn-server-events ' + str(pipe_fd),
        '--client-disconnect', 'openvpn-server-events ' + str(pipe_fd),
        '--dh', utils.config.dh,
        '--max-clients', str(utils.config.max_clients),
        *args, **kw)

def client(serverIp, pipe_fd, *args, **kw):
    utils.log('Starting client', 5)
    return openvpn(
        '--nobind',
        '--client',
        '--remote', serverIp,
        '--up', 'openvpn-up-client',
        '--route-up', 'openvpn-route-up ' + str(pipe_fd),
        *args, **kw)

def babel(**kw):
    utils.log('Starting babel', 3)
    args = ['babeld',
            '-C', 'redistribute local ip %s' % (utils.config.internal_ip),
            '-C', 'redistribute local deny',
            # Route VIFIB ip adresses
            '-C', 'in ip %s::/%u' % (utils.ipFromBin(utils.config.vifibnet), len(utils.config.vifibnet)),
            # Route only addresse in the 'local' network,
            # or other entire networks
            #'-C', 'in ip %s' % (config.internal_ip),
            #'-C', 'in ip ::/0 le %s' % network_mask,
            # Don't route other addresses
            '-C', 'in deny',
            '-d', str(utils.config.verbose),
            '-s',
            ]
    if utils.config.babel_state:
        args += '-S', utils.config.babel_state
    args = args + ['vifibnet'] + list(tunnelmanager.free_interface_set)
    utils.log(str(args), 5)
    return subprocess.Popen(args, **kw)

