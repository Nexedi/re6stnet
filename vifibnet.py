#!/usr/bin/env python
import argparse, errno, math, os, select, subprocess, sys, time
from OpenSSL import crypto
import traceback
import upnpigd
import openvpn
import utils
import db
import tunnelmanager

def startBabel(**kw):
    args = ['babeld',
            '-C', 'redistribute local ip %s' % (config.internal_ip),
            '-C', 'redistribute local deny',
            # Route VIFIB ip adresses
            '-C', 'in ip %s::/%u' % (utils.ipFromBin(config.vifibnet), len(config.vifibnet)),
            # Route only addresse in the 'local' network,
            # or other entire networks
            #'-C', 'in ip %s' % (config.internal_ip),
            #'-C', 'in ip ::/0 le %s' % network_mask,
            # Don't route other addresses
            '-C', 'in deny',
            '-d', str(config.verbose),
            '-s',
            ]
    if config.babel_state:
        args += '-S', config.babel_state
    args = args + ['vifibnet'] + list(tunnelmanager.free_interface_set)
    if config.verbose >= 5:
        print args
    return subprocess.Popen(args, **kw)

def getConfig():
    global config
    parser = argparse.ArgumentParser(
            description='Resilient virtual private network application')
    _ = parser.add_argument
    # Server address MUST be a vifib address ( else requests will be denied )
    _('--server', required=True,
            help='Address for peer discovery server')
    _('--server-port', required=True, type=int,
            help='Peer discovery server port')
    _('-l', '--log', default='/var/log',
            help='Path to vifibnet logs directory')
    _('--client-count', default=2, type=int,
            help='Number of client connections')
    # TODO: use maxpeer
    _('--max-clients', default=10, type=int,
            help='the number of peers that can connect to the server')
    _('--refresh-time', default=300, type=int,
            help='the time (seconds) to wait before changing the connections')
    _('--refresh-count', default=1, type=int,
            help='The number of connections to drop when refreshing the connections')
    _('--db', default='/var/lib/vifibnet/peers.db',
            help='Path to peers database')
    _('--dh', required=True,
            help='Path to dh file')
    _('--babel-state', default='/var/lib/vifibnet/babel_state',
            help='Path to babeld state-file')
    _('--verbose', '-v', default=0, type=int,
            help='Defines the verbose level')
    _('--ca', required=True,
            help='Path to the certificate authority file')
    _('--cert', required=True,
            help='Path to the certificate file')
    _('--ip', required=True, dest='external_ip',
            help='Ip address of the machine on the internet')
    # Openvpn options
    _('openvpn_args', nargs=argparse.REMAINDER,
            help="Common OpenVPN options (e.g. certificates)")
    openvpn.config = config = parser.parse_args()
    tunnelmanager.config = config
    db.config = config
    utils.verbose = config.verbose

    # Get network prefix from ca.crt
    with open(config.ca, 'r') as f:
        ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        config.vifibnet = bin(ca.get_serial_number())[3:]

    # Get ip from cert.crt
    with open(config.cert, 'r') as f:
        cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        subject = cert.get_subject()
        prefix, prefix_len = subject.CN.split('/')
        config.internal_ip = utils.ipFromPrefix(config.vifibnet, prefix, int(prefix_len))
        utils.log('Intranet ip : %s' % (config.internal_ip,), 3)

    # Treat openvpn arguments
    if config.openvpn_args[0] == "--":
        del config.openvpn_args[0]
    config.openvpn_args.append('--ca')
    config.openvpn_args.append(config.ca)
    config.openvpn_args.append('--cert')
    config.openvpn_args.append(config.cert)

    utils.log("Configuration completed", 1)

def handle_message(msg):
    script_type, arg = msg.split()
    if script_type == 'client-connect':
        utils.log('Incomming connection from %s' % (arg,), 3)
        # TODO: check if we are not already connected to it
    elif script_type == 'client-disconnect':
        utils.log('%s has disconnected' % (arg,), 3)
    elif script_type == 'route-up':
        # TODO: save the external ip received
        utils.log('External Ip : ' + arg, 3)
    else:
        utils.log('Unknow message recieved from the openvpn pipe : ' + msg, 1)

def main():
    # Get arguments
    getConfig()

    # Setup database
    tunnelmanager.peers_db = db.PeersDB(config.db)

    # Launch babel on all interfaces. WARNING : you have to be root to start babeld
    utils.log('Starting babel', 3)
    babel = startBabel(stdout=os.open(os.path.join(config.log, 'vifibnet.babeld.log'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC), stderr=subprocess.STDOUT)

    # Create and open read_only pipe to get connect/disconnect events from openvpn
    utils.log('Creating pipe for openvpn events', 3)
    r_pipe, write_pipe = os.pipe()
    read_pipe = os.fdopen(r_pipe)

    # Establish connections
    utils.log('Starting openvpn server', 3)
    serverProcess = openvpn.server(config.internal_ip, write_pipe, '--dev', 'vifibnet',
            stdout=os.open(os.path.join(config.log, 'vifibnet.server.log'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC))
    tunnelmanager.startNewConnections(config.client_count, write_pipe)

    # Timed refresh initializing
    next_refresh = time.time() + config.refresh_time

    # TODO: use peers_db.populate(100) every once in a while ?
    # main loop
    try:
        while True:
            ready, tmp1, tmp2 = select.select([read_pipe], [], [],
                    max(0, next_refresh - time.time()))
            if ready:
                handle_message(read_pipe.readline())
            if time.time() >= next_refresh:
                tunnelmanager.peers_db.populate(10)
                refreshConnections(write_pipe)
                next_refresh = time.time() + config.refresh_time
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    main()

