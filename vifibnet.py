#!/usr/bin/env python
import argparse, errno, math, os, select, subprocess, sys, time, traceback, upnpigd
from OpenSSL import crypto
import db, plib, upnpigd, utils, tunnel

def getConfig():
    parser = argparse.ArgumentParser(
            description='Resilient virtual private network application')
    _ = parser.add_argument
    # Server address MUST be a vifib address ( else requests will be denied )
    _('--server', required=True,
            help='Address for peer discovery server')
    _('--server-port', required=True, type=int,
            help='Peer discovery server port')
    _('-log', '-l', default='/var/log',
            help='Path to vifibnet logs directory')
    _('--tunnel-refresh', default=300, type=int,
            help='the time (seconds) to wait before changing the connections')
    _('--peers-db-refresh', default=3600, type=int,
            help='the time (seconds) to wait before refreshing the peers db')
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
    _('--ip', default=None, dest='external_ip',
            help='Ip address of the machine on the internet')
    _('--internal-port', default=1194,
            help='The internal port to listen on for incomming connections')
    _('--external-port', default=1194,
            help='The external port to advertise for other peers to connect')
    _('--proto', default='udp',
            help='The protocol to use for the others peers to connect')
    # args to be removed ?
    _('--connection-count', default=30, type=int,
            help='Number of client connections')
    _('--refresh-rate', default=0.05, type=float,
            help='The ratio of connections to drop when refreshing the connections')
    # Openvpn options
    _('openvpn_args', nargs=argparse.REMAINDER,
            help="Common OpenVPN options (e.g. certificates)")
    return parser.parse_args()

def main():
    # Get arguments
    config = getConfig()
    network = utils.networkFromCa(config.ca)
    internal_ip = utils.ipFromCert(network, config.cert)
    openvpn_args = utils.ovpnArgs(config.openvpn_args, config.ca, config.cert)

    # Set global variables
    tunnel.log = config.log
    utils.verbose = plib.verbose = config.verbose

    # Create and open read_only pipe to get server events
    utils.log('Creating pipe for server events', 3)
    r_pipe, write_pipe = os.pipe()
    read_pipe = os.fdopen(r_pipe)

    # Init db and tunnels
    if config.external_ip == None:
        try:
            config.external_ip, config.external_port = upnpigd.ForwardViaUPnP(config.internal_port)
        except Exception:
            utils.log('An atempt to forward a port via UPnP failed', 5)

    peer_db = db.PeerManager(config.db, config.server, config.server_port, config.peers_db_refresh,
            config.external_ip, internal_ip, config.external_port, config.proto, 200)
    tunnel_manager = tunnel.TunnelManager(write_pipe, peer_db, openvpn_args, config.tunnel_refresh, config.connection_count, config.refresh_rate)

    # Launch babel on all interfaces. WARNING : you have to be root to start babeld
    interface_list = ['vifibnet'] + list(tunnel_manager.free_interface_set)
    router = plib.router(network, internal_ip, interface_list,
        stdout=os.open(os.path.join(config.log, 'vifibnet.babeld.log'),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC), stderr=subprocess.STDOUT)

   # Establish connections
    server_process = plib.server(internal_ip, network, config.connection_count, config.dh, write_pipe,
            config.internal_port, config.proto, '--dev', 'vifibnet', *openvpn_args,
            stdout=os.open(os.path.join(config.log, 'vifibnet.server.log'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC))

    # main loop
    try:
        while True:
            ready, tmp1, tmp2 = select.select([read_pipe], [], [],
                    max(0, min(tunnel_manager.next_refresh, peer_db.next_refresh) - time.time()))
            if ready:
                peer_db.handle_message(read_pipe.readline())
            if time.time() >= peer_db.next_refresh:
                peer_db.refresh()
            if time.time() >= tunnel_manager.next_refresh:
                tunnel_manager.refresh()
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    main()

