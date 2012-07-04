#!/usr/bin/env python
import argparse, errno, os, subprocess, sys, time
import upnpigd
import openvpn

VIFIB_NET = "2001:db8:42::/48"


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

def getConfig():
    global config
    parser = argparse.ArgumentParser(description='Resilient virtual private network application')
    _ = parser.add_argument
    _('--dh', required=True, help='Path to dh file')
    _('--babel-state', help='Path to babeld state-file')
    _('--verbose', '-v', default='0', help='Defines the verbose level')
    _('--ca', required=True, help='Path to the certificate authority')
    _('--key', required=True, help='Path to the rsa_key')
    _('--cert', required=True, help='Pah to the certificate')
    # Temporary args
    _('--ip', required=True, help='IPv6 of the server')
    config = parser.parse_args()


def main():
    getConfig()
    if config.ip != 'none':
        serverProcess = openvpn.server(config, config.ip)
    else:
        client1Process = openvpn.client(config, '10.1.4.2')
    

if __name__ == "__main__":
    main()

