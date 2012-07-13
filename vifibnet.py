#!/usr/bin/env python
import argparse, errno, math, os, select, sqlite3, subprocess, sys, time, xmlrpclib
from OpenSSL import crypto
import traceback
import upnpigd
import openvpn
import random
import log

connection_dict = {} # to remember current connections we made
free_interface_set = set(('client1', 'client2', 'client3', 'client4', 'client5',
                          'client6', 'client7', 'client8', 'client9', 'client10'))

# TODO: flag in some way the peers that are connected to us so we don't connect to them
# Or maybe we just don't care

class PeersDB:
    def __init__(self, dbPath):

        log.log('Connectiong to peers database', 4)
        self.db = sqlite3.connect(dbPath, isolation_level=None)
        log.log('Preparing peers database', 4)
        try:
            self.db.execute("UPDATE peers SET used = 0")
        except sqlite3.OperationalError, e:
            if e.args[0] != 'no such table: peers':
                raise RuntimeError

    def populate(self, n):
        log.log('Connecting to remote server', 3)
        self.proxy = xmlrpclib.ServerProxy('http://%s:%u' % (config.server, config.server_port))
        log.log('Populating Peers DB', 2)
        # TODO: determine port and proto
        port = 1194
        proto = 'udp'
        new_peer_list = self.proxy.getPeerList(n, (config.external_ip, port, proto))
        self.db.executemany("INSERT OR REPLACE INTO peers (ip, port, proto) VALUES (?,?,?)", new_peer_list)
        self.db.execute("DELETE FROM peers WHERE ip = ?", (config.external_ip,))

    def getUnusedPeers(self, nPeers):
        return self.db.execute("SELECT id, ip, port, proto FROM peers WHERE used = 0 "
                "ORDER BY RANDOM() LIMIT ?", (nPeers,))

    def usePeer(self, id):
        log.log('Updating peers database : using peer ' + str(id), 5)
        self.db.execute("UPDATE peers SET used = 1 WHERE id = ?", (id,))

    def unusePeer(self, id):
        log.log('Updating peers database : unusing peer ' + str(id), 5)
        self.db.execute("UPDATE peers SET used = 0 WHERE id = ?", (id,))

def ipFromBin(prefix):
    prefix = hex(int(prefix, 2))[2:]
    ip = ''
    for i in xrange(0, len(prefix) - 1, 4):
        ip += prefix[i:i+4] + ':'
    return ip.rstrip(':')

def ipFromPrefix(prefix, prefix_len):
    prefix = bin(int(prefix))[2:].rjust(prefix_len, '0')
    ip_t = (config.vifibnet + prefix).ljust(128, '0')
    return ipFromBin(ip_t)

def startBabel(**kw):
    args = ['babeld',
            '-C', 'redistribute local ip %s' % (config.internal_ip),
            '-C', 'redistribute local deny',
            # Route VIFIB ip adresses
            '-C', 'in ip %s::/%u' % (ipFromBin(config.vifibnet), len(config.vifibnet)),
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
    return subprocess.Popen(args + ['vifibnet'] + list(free_interface_set), **kw)

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
    _('--refresh-time', default=60, type=int,
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
    log.verbose = config.verbose
    # Get network prefix from ca.crt
    with open(config.ca, 'r') as f:
        ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        config.vifibnet = bin(ca.get_serial_number())[3:]
    # Get ip from cert.crt
    with open(config.cert, 'r') as f:
        cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        subject = cert.get_subject()
        prefix, prefix_len = subject.serialNumber.split('/')
        config.internal_ip = ipFromPrefix(prefix, int(prefix_len))
        log.log('Intranet ip : %s' % (config.internal_ip,), 3)
    # Treat openvpn arguments
    if config.openvpn_args[0] == "--":
        del config.openvpn_args[0]
    config.openvpn_args.append('--ca')
    config.openvpn_args.append(config.ca)
    config.openvpn_args.append('--cert')
    config.openvpn_args.append(config.cert)

    log.log("Configuration completed", 1)

def startNewConnection(n, write_pipe):
    try:
        for peer_id, ip, port, proto in peers_db.getUnusedPeers(n):
            log.log('Establishing a connection with id %s (%s:%s)' % (peer_id, ip, port), 2)
            iface = free_interface_set.pop()
            connection_dict[peer_id] = ( openvpn.client( ip, write_pipe, '--dev', iface, '--proto', proto, '--rport', str(port),
                stdout=os.open(os.path.join(config.log, 'vifibnet.client.%s.log' % (peer_id,)), 
                               os.O_WRONLY|os.O_CREAT|os.O_TRUNC) ),
                iface)
            peers_db.usePeer(peer_id)
    except KeyError:
        log.log("Can't establish connection with %s : no available interface" % ip, 2)
    except Exception:
        traceback.print_exc()

def killConnection(peer_id):
    try:
        log.log('Killing the connection with id ' + str(peer_id), 2)
        p, iface = connection_dict.pop(peer_id)
        p.kill()
        free_interface_set.add(iface)
        peers_db.unusePeer(peer_id)
    except KeyError:
        log.log("Can't kill connection to " + peer_id + ": no existing connection", 1)
        pass
    except Exception:
        log.log("Can't kill connection to " + peer_id + ": uncaught error", 1)
        pass

def checkConnections():
    for id in connection_dict.keys():
        p, iface = connection_dict[id]
        if p.poll() != None:
            log.log('Connection with %s has failed with return code %s' % (id, p.returncode), 3)
            free_interface_set.add(iface)
            peers_db.unusePeer(id)
            del connection_dict[id]

def refreshConnections(write_pipe):
    checkConnections()
    # Kill some random connections
    try:
        for i in range(0, max(0, len(connection_dict) - config.client_count + config.refresh_count)):
            peer_id = random.choice(connection_dict.keys())
            killConnection(peer_id)
    except Exception:
        pass
    # Establish new connections
    startNewConnection(config.client_count - len(connection_dict), write_pipe)

def handle_message(msg):
    script_type, arg = msg.split()
    if script_type == 'client-connect':
        log.log('Incomming connection from %s' % (arg,), 3)
        # TODO: check if we are not already connected to it
    elif script_type == 'client-disconnect':
        log.log('%s has disconnected' % (arg,), 3)
    elif script_type == 'ipchange':
        # TODO: save the external ip received
        log.log('External Ip : ' + arg, 3)
    else:
        log.log('Unknow message recieved from the openvpn pipe : ' + msg, 1)

def main():
    # Get arguments
    getConfig()
    log.verbose = config.verbose
    # TODO: how do we decide which protocol we use ?
    # (externalIp, externalPort) = upnpigd.GetExternalInfo(1194)

    # Setup database
    global peers_db # stop using global variables for everything ?
    peers_db = PeersDB(config.db)

    # Launch babel on all interfaces. WARNING : you have to be root to start babeld
    log.log('Starting babel', 3)
    babel = startBabel(stdout=os.open(os.path.join(config.log, 'vifibnet.babeld.log'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC), stderr=subprocess.STDOUT)

    # Create and open read_only pipe to get connect/disconnect events from openvpn
    log.log('Creating pipe for openvpn events', 3)
    r_pipe, write_pipe = os.pipe()
    read_pipe = os.fdopen(r_pipe)

    # Establish connections
    log.log('Starting openvpn server', 3)
    serverProcess = openvpn.server(config.internal_ip, write_pipe, '--dev', 'vifibnet',
            stdout=os.open(os.path.join(config.log, 'vifibnet.server.log'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC))
    startNewConnection(config.client_count, write_pipe)

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
                refreshConnections(write_pipe)
                next_refresh = time.time() + config.refresh_time
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    main()

