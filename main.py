#!/usr/bin/env python
import argparse, errno, os, select, sqlite3, subprocess, sys, time
import traceback
import upnpigd
import openvpn
import random

VIFIB_NET = "2001:db8:42::/48"
connection_dict = {} # to remember current connections we made
client_set = set([]) # to remember current connections other made
free_interface_set = set(('client1', 'client2', 'client3', 'client4', 'client5',
                          'client6', 'client7', 'client8', 'client9', 'client10'))

def log_message(message, verbose_level):
    if config.verbose >= verbose_level:
        print time.strftime("%d-%m-%Y %H:%M:%S : " + message)

# TODO : How do we get our vifib ip ?
# TODO : flag in some way the peers that are connected to us so we don't connect to them
# Or maybe we just don't care, 
class PeersDB:
    def __init__(self, dbPath):
        log_message('Connectiong to peers database', 4)
        self.db = sqlite3.connect(dbPath, isolation_level=None)
        log_message('Initializing peers database', 4)
        self.db.execute("""CREATE TABLE IF NOT EXISTS peers
                        ( id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ip TEXT NOT NULL,
                        port INTEGER NOT NULL,
                        proto TEXT NOT NULL,
                        used INTEGER NOT NULL)""")
        self.db.execute("CREATE INDEX IF NOT EXISTS _peers_used ON peers(used)")
        self.db.execute("UPDATE peers SET used = 0")
    
    def getUnusedPeers(self, nPeers):
        return self.db.execute("SELECT id, ip, port, proto FROM peers WHERE used = 0 "
                "ORDER BY RANDOM() LIMIT ?", (nPeers,))

    def usePeer(self, id):
        log_message('Updating peers database : using peer ' + str(id), 5)
        self.db.execute("UPDATE peers SET used = 1 WHERE id = ?", (id,))
    
    def unusePeer(self, id):
        log_message('Updating peers database : unusing peer ' + str(id), 5)
        self.db.execute("UPDATE peers SET used = 0 WHERE id = ?", (id,))



def babel(network_ip, network_mask, verbose_level):
    args = ['babeld',
            '-C', 'redistribute local ip %s/%s' % (network_ip, network_mask),
            '-C', 'redistribute local deny',
            # Route VIFIB ip adresses
            '-C', 'in ip %s' % VIFIB_NET,
            # Route only addresse in the 'local' network,
            # or other entire networks
            '-C', 'in ip %s/%s' % (network_ip,network_mask),
            #'-C', 'in ip ::/0 le %s' % network_mask,
            # Don't route other addresses
            '-C', 'in ip deny',
            '-d', str(verbose_level),
            '-s',
            ]
    if config.babel_state:
        args += '-S', config.babel_state
    log_message("Starting babel daemon",2)
    return subprocess.Popen(args + list(free_interface_set))

def getConfig():
    global config
    parser = argparse.ArgumentParser(
            description='Resilient virtual private network application')
    _ = parser.add_argument
    _('--server-log', default='/var/log/vifibnet.server.log',
            help='Path to openvpn server log file')
    _('--client-log', default='/var/log/',
            help='Path to openvpn client log directory')
    _('--client-count', default=2, type=int,
            help='the number servers the peers try to connect to')
    _('--max-clients', default=10, type=int,
            help='the number of peers that can connect to the server')
    _('--refresh-time', default=20, type=int,
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
    # Temporary args
    _('--ip', required=True,
            help='IPv6 of the server')
    # Openvpn options
    _('openvpn_args', nargs=argparse.REMAINDER,
            help="Common OpenVPN options (e.g. certificates)")
    openvpn.config = config = parser.parse_args()
    if config.openvpn_args[0] == "--":
        del config.openvpn_args[0]

def startNewConnection(n):
    try:
        for id, ip, port, proto in peers_db.getUnusedPeers(n):
            log_message('Establishing a connection with id %s (%s:%s)' % (id,ip,port), 2)
            iface = free_interface_set.pop()
            connection_dict[id] = ( openvpn.client( ip, '--dev', iface, '--proto', proto, '--rport', str(port),
                stdout=os.open(config.client_log + 'vifibnet.client.' + str(id) + '.log', os.O_WRONLY|os.O_CREAT|os.O_TRUNC) ) , iface)
            peers_db.usePeer(id)
    except KeyError:
        log_message("Can't establish connection with %s : no available interface" % ip, 2)
        pass
    except Exception:
        traceback.print_exc()

def killConnection(id):
    try:
        log_message('Killing the connection with id ' + str(id), 2)
        p, iface = connection_dict.pop(id)
        p.kill()
        free_interface_set.add(iface)
        peers_db.unusedPeer(id)
    except KeyError:
        log_message("Can't kill connection to " + peer + ": no existing connection", 1)
        pass
    except Exception:
        log_message("Can't kill connection to " + peer + ": uncaught error", 1)
        pass

def checkConnections():
    toDel = set([])
    for id in connection_dict.keys():
        p, iface = connection_dict[id]
        if p.poll() != None:
            log_message('Connection with ' + str(id) + ' has failed with return code ' + str(p.returncode) , 3)
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
    words = msg.split()
    if words[0] == 'CLIENT_CONNECTED':
        log_message('Incomming connection from ' + words[1], 3)
        client_set.push(words[1])
        # TODO :  check if we are not already connected to it
    elif words[0] == 'CLIENT_DISCONNECTED':
        log_message(words[1] + ' has disconnected', 3)
        client_set.pop(words[1])
    else:
        log_message('Unknow message recieved from the openvpn pipe : ' + msg, 1)

def main():
    # Get arguments
    getConfig()
    (externalIp, externalPort) = upnpigd.GetExternalInfo(1194)

    # Setup database
    global peers_db # stop using global variables for everything ?
    peers_db = PeersDB(config.db)

    # Create and open read_only pipe to get connect/disconnect events from openvpn
    log_message('Creating pipe for openvpn events', 3)
    r_pipe, write_pipe = os.pipe()
    read_pipe = os.fdopen(r_pipe)

    # Establish connections
    log_message('Starting openvpn server', 3)
    serverProcess = openvpn.server(config.ip, write_pipe,
            '--dev', 'vifibnet', 
            stdout=os.open(config.server_log, os.O_WRONLY|os.O_CREAT|os.O_TRUNC))
    startNewConnection(config.client_count)
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

# TODO : remove incomming connections from avalaible peers

