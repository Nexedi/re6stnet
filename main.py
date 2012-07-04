#!/usr/bin/env python
import argparse, errno, os, subprocess, sys, time
import upnpigd
import openvpn
import random

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
    # connections establishement
    _('--max-peer', help='the number of peers that can connect to the server', default='10')
        # TODO : use it
    _('--client-count', help='the number servers the peers try to connect to', default = '2')
    _('--refresh-time', help='the time (seconds) to wait before changing the connections', default = '20')
        # TODO : use it
    _('--refresh-count', help='The number of connections to drop when refreshing the connections', default='1')
        # TODO : use it
    # Temporary args
    _('--ip', required=True, help='IPv6 of the server')
    config = parser.parse_args()

def startNewConnection():
    try:
        peer = random.choice(avalaiblePeers.keys())
        if config.verbose > 2:
            print 'Establishing a connection with ' + peer
        del avalaiblePeers[peer]
        connections[peer] = openvpn.client(config, peer)
    except Exception:
        pass

# TODO :
def killConnection(peer):
    if config.verbose > 2:
        print 'Killing the connection with ' + peer
    subprocess.Popen.kill(connections[peer])
    del connections[peer]
    avalaiblePeers[peer] = 1194 # TODO : give the real port


def refreshConnections():
    try:
        for i in range(0, int(config.refresh_count)):
            peer = random.choice(connections.keys())
            killConnection(peer)
    except Exception:
        pass

    for i in range(len(connections),  int(config.client_count)):
        startNewConnection()
    

def main():
    # init variables
    global connections
    global avalaiblePeers # the list of peers we can connect to
    avalaiblePeers = { '10.1.4.2' : 1194, '10.1.4.3' : 1194, '10.1.3.2' : 1194 }
    connections = {} # to remember current connections
    getConfig()
    (externalIp, externalPort) = upnpigd.GetExternalInfo(1194)
    try:
        del avalaiblePeers[externalIp]
    except Exception:
        pass

    # establish connections
    serverProcess = openvpn.server(config, config.ip)
    for i in range(0, int(config.client_count)):
        startNewConnection()
    
    # main loop
    try:
        while True:
            time.sleep(float(config.refresh_time))
            refreshConnections()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()

# TODO : pass the remote port as an argument to openvpn
# TODO : remove incomming connections from avalaible peers

