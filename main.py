#!/usr/bin/env python
import argparse, errno, os, subprocess, sys, time
import upnpigd

VIFIB_NET = "2001:db8:42::/48"

def openvpn(*args, **kw):
    args = ['openvpn',
        '--dev', 'tap',
        '--ca', ca_path,
        '--cert', cert_path,
        '--key', key_path,
        '--nobind',
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
    return openvpn(remote=ip, *args, **kw)

# How do we get our vifib_ip ?

def babel(network_ip, network_mask, verbose_level):
    args = [ '-S', '/var/lib/babeld/state',
            '-I', 'redistribute local ip %s/%s' % (network_ip,network_mask),
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
            '-s'
            ]
    return Popen(args)

def main():
    parser = argparse.ArgumentParser(
            description="Resilient virtual private network application")
    _ = parser.add_argument
    _('--ca', required=True,
            help="Path to ca.crt file")
    _('--cert', required=True,
            help="Path to host certificate file")
    _('--key', required=True,
            help="Path to host key file")
    _('--dh', required=True,
            help="Path to dh file")
    _('--verbose', '-v', action='count',
            help="Defines the verbose level")
    args=parser.parse_args()
    # how to setup openvpn connections :
    server = server(dev='server', verb=3)
    pass

if __name__ == "__main__":
    main()

