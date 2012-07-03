#!/usr/bin/env python
import argparse, errno, os, subprocess, sys, time
import upnpigd

VIFIB_NET = "2001:db8:42::/48"

# TODO : - should we use slapos certificates or
#          use new ones we create for openvpn ?

def openvpn(*args, **kw):
    args = ['openvpn',
        '--dev', 'tap',
        '--ca', config.ca,
        '--cert', config.cert,
        '--key', config.key,
        '--persist-tun',
        '--persist-key',
        '--user' 'nobody',
        '--group', 'nogroup',
        ] + list(args)
    #stdin = kw.pop('stdin', None)
    #stdout = kw.pop('stdout', None)
    #stderr = kw.pop('stderr', None)
    for i in kw.iteritems():
        args.append('--%s=%s' % i)
    return subprocess.Popen(args,
         #stdin=stdin, stdout=stdout, stderr=stderr,
         )

# TODO : set iface up when creating a server/client
# ! check working directory before launching up script ?

def server(*args, **kw):
    return openvpn(
         '--tls-server',
         '--client-to-client',
         #'--keepalive', '10', '60',
         mode='server',
         dh=dh_path,
         *args, **kw)

def client(ip, *args, **kw):
    return openvpn('--nobind', remote=ip, *args, **kw)

# TODO : How do we get our vifib ip ?

def babel(network_ip, network_mask, verbose_level):
    args = ['-I', 'redistribute local ip %s/%s' % (network_ip, network_mask),
            '-I', 'redistribute local deny',
            # Route VIFIB ip adresses
            '-I', 'in ip %s' % VIFIB_NET,
            # Route only addresse in the 'local' network,
            # or other entire networks
            #'-I', 'in ip %s/%s' % (network_ip,network_mask),
            #'-I', 'in ip ::/0 le %s' % network_mask,
            # Don't route other addresses
            '-I', 'in ip deny',
            '-d', str(verbose_level),
            '-s',
            ]
    if config.babel_state:
        args += '-S', config.babel_state
    # TODO : add list of interfaces to use with babel
    return Popen(args)

def main():
    global config
    parser = argparse.ArgumentParser(
            description="Resilient virtual private network application")
    _ = parser.add_argument
    _('--dh', required=True,
            help="Path to dh file")
    _('--babel-state',
            help="Path to babeld state-file")
    #_('--verbose', '-v', action='count',
    #        help="Defines the verbose level")
    _('openvpn_args', nargs=argparse.REMAINDER,
            help="Common OpenVPN options (e.g. certificates)")
    config = parser.parse_args()
    # TODO : set the certificates and ker paths, in global variables
    # how to setup openvpn connections :
    server = server(dev='server', verb=3)

if __name__ == "__main__":
    main()

