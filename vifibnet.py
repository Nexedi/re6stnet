#!/usr/bin/env python
import argparse, errno, os, select, sqlite3, subprocess, sys, time, xmlrpclib
import traceback
import upnpigd
import openvpn
import random
import log

VIFIB_NET = "2001:db8:42::/48"
connection_dict = {} # to remember current connections we made
free_interface_set = set(('client1', 'client2', 'client3', 'client4', 'client5',
                          'client6', 'client7', 'client8', 'client9', 'client10'))

# TODO : flag in some way the peers that are connected to us so we don't connect to them
# Or maybe we just don't care,
class PeersDB:
    def __init__(self, dbPath):
        self.proxy = xmlrpclib.ServerProxy('http://%s:%u' % (config.server, config.server_port))

        log.log('Connectiong to peers database', 4)
        self.db = sqlite3.connect(dbPath, isolation_level=None)
        log.log('Initializing peers database', 4)
        try:
            self.db.execute("""CREATE TABLE peers (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            ip TEXT NOT NULL,
                            port INTEGER NOT NULL,
                            proto TEXT NOT NULL,
                            used INTEGER NOT NULL default 0)""")
            self.db.execute("CREATE INDEX _peers_used ON peers(used)")
            self.db.execute("UPDATE peers SET used = 0")
        except sqlite3.OperationalError, e:
            if e.args[0] != 'table peers already exists':
                raise RuntimeError
        else:
            self.populateDB(100)

    def populateDB(self, n):
        self.db.executemany("INSERT INTO peers (ip, port, proto) VALUES ?", self.proxy.getPeerList(n))

    def getUnusedPeers(self, nPeers):
        return self.db.execute("SELECT id, ip, port, proto FROM peers WHERE used = 0 "
                "ORDER BY RANDOM() LIMIT ?", (nPeers,))

    def usePeer(self, id):
        log.log('Updating peers database : using peer ' + str(id), 5)
        self.db.execute("UPDATE peers SET used = 1 WHERE id = ?", (id,))

    def unusePeer(self, id):
        log.log('Updating peers database : unusing peer ' + str(id), 5)
        self.db.execute("UPDATE peers SET used = 0 WHERE id = ?", (id,))

def ipFromPrefix(prefix, prefix_len):
    tmp = hew(int(prefix, 2))[2::]
    ip = VIFIB_NET
    for i in xrange(0, len(ip), 4):
        ip += tmp[i:i+4] + ':'
    ip += ':'

def startBabel(**kw):
    args = ['babeld',
            '-C', 'redistribute local ip %s' % (config.ip),
            '-C', 'redistribute local deny',
            # Route VIFIB ip adresses
            '-C', 'in ip %s' % VIFIB_NET,
            # Route only addresse in the 'local' network,
            # or other entire networks
            #'-C', 'in ip %s' % (config.ip),
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
    _('--server', required=True,
            help='Address for peer discovery server')
    _('--server-port', required=True,
            help='Peer discovery server port')
    _('--log-directory', default='/var/log',
            help='Path to vifibnet logs directory')
    _('--client-count', default=2, type=int,
            help='Number of client connections')
    # TODO : use maxpeer
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
    _('--cert', required=True,
            help='Path to the certificate file')
    # Temporary args - to be removed
    _('--ip', required=True,
            help='IPv6 of the server')
    # Openvpn options
    _('openvpn_args', nargs=argparse.REMAINDER,
            help="Common OpenVPN options (e.g. certificates)")
    openvpn.config = config = parser.parse_args()
    with open(config.cert, 'r') as f:
        cert = crypto.load_certificate(crypto.FILETYPE_PEM, f)
        subject = cert.get_subject()
        prefix_txt, prefix_len_txt = subject.serialNumber.split('/')
        prefix = int(prefix_txt)
        prefix_len = int(prefix_len_txt)
        ip = ipFromPrefix(prefix)
        print ip
    if config.openvpn_args[0] == "--":
        del config.openvpn_args[0]
    config.openvpn_args.append('--cert')
    config.openvpn_args.append(config.cert)

def startNewConnection(n):
    try:
        for id, ip, port, proto in peers_db.getUnusedPeers(n):
            log.log('Establishing a connection with id %s (%s:%s)' % (id,ip,port), 2)
            iface = free_interface_set.pop()
            connection_dict[id] = ( openvpn.client( ip, '--dev', iface, '--proto', proto, '--rport', str(port),
                stdout=os.open(os.path.join(config.log_directory, 'vifibnet.client.%s.log' % (id,)), 
                               os.O_WRONLY|os.O_CREAT|os.O_TRUNC) ),
                iface)
            peers_db.usePeer(id)
    except KeyError:
        log.log("Can't establish connection with %s : no available interface" % ip, 2)
        pass
    except Exception:
        traceback.print_exc()

def killConnection(id):
    try:
        log.log('Killing the connection with id ' + str(id), 2)
        p, iface = connection_dict.pop(id)
        p.kill()
        free_interface_set.add(iface)
        peers_db.unusePeer(id)
    except KeyError:
        log.log("Can't kill connection to " + peer + ": no existing connection", 1)
        pass
    except Exception:
        log.log("Can't kill connection to " + peer + ": uncaught error", 1)
        pass

def checkConnections():
    for id in connection_dict.keys():
        p, iface = connection_dict[id]
        if p.poll() != None:
            log.log('Connection with %s has failed with return code %s' % (id, p.returncode), 3)
            free_interface_set.add(iface)
            peers_db.unusePeer(id)
            del connection_dict[id]

def refreshConnections():
    checkConnections()
    # Kill some random connections
    try:
        for i in range(0, max(0, len(connection_dict) - config.client_count + config.refresh_count)):
            id = random.choice(connection_dict.keys())
            killConnection(id)
    except Exception:
        pass
    # Establish new connections
    startNewConnection(config.client_count - len(connection_dict))

def handle_message(msg):
    script_type, common_name = msg.split()
    if script_type == 'client-connect':
        log.log('Incomming connection from %s' % (common_name,), 3)
        # TODO :  check if we are not already connected to it
    elif script_type == 'client-disconnect':
        log.log('%s has disconnected' % (common_name,), 3)
    else:
        log.log('Unknow message recieved from the openvpn pipe : ' + msg, 1)

def main():
    # Get arguments
    getConfig()
    log.verbose = config.verbose
    (externalIp, externalPort) = upnpigd.GetExternalInfo(1194)

    # Setup database
    global peers_db # stop using global variables for everything ?
    peers_db = PeersDB(config.db)

    # Launch babel on all interfaces
    log.log('Starting babel', 3)
    babel = startBabel(stdout=os.open('%s/babeld.log' % (config.log_directory,), os.O_WRONLY | os.O_CREAT | os.O_TRUNC),
                        stderr=subprocess.STDOUT)

    # Create and open read_only pipe to get connect/disconnect events from openvpn
    log.log('Creating pipe for openvpn events', 3)
    r_pipe, write_pipe = os.pipe()
    read_pipe = os.fdopen(r_pipe)

    # Establish connections
    log.log('Starting openvpn server', 3)
    serverProcess = openvpn.server(config.ip, write_pipe, '--dev', 'vifibnet',
            stdout=os.open(os.path.join(config.log_directory, 'vifibnet.server.log'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC))
    startNewConnection(config.client_count)

    # Timed refresh initializing
    next_refresh = time.time() + config.refresh_time

    # main loop
    try:
        while True:
            ready, tmp1, tmp2 = select.select([read_pipe], [], [], 
                    max(0, next_refresh - time.time()))
            if ready:
                handle_message(read_pipe.readline())
            if time.time() >= next_refresh:
                refreshConnections()
                next_refresh = time.time() + config.refresh_time
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    main()

