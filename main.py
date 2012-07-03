#!/usr/bin/env python
import argparse, errno, os, subprocess, sys, time
import upnpigd

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

def main():
    server = openvpn.server(dev="server",  verb=3 )
    pass

if __name__ == "__main__":
    main()

