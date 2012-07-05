#!/usr/bin/env python
import argparse, errno, os, sqlite3, subprocess, sys, time
import traceback
import upnpigd
import openvpn
import random

VIFIB_NET = "2001:db8:42::/48"
connection_dict = {} # to remember current connections
free_interface_set = set(('client1', 'client2', 'client3', 'client4', 'client5', 'client6', 'client7', 'client8', 'client9', 'client10'))

# TODO : How do we get our vifib ip ?

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
    return subprocess.Popen(args + list(free_interface_set))

def getConfig():
    global config
    parser = argparse.ArgumentParser(
            description='Resilient virtual private network application')
    _ = parser.add_argument
    _('--client-count', default=2, type=int,
            help='the number servers the peers try to connect to')
    # TODO : use maxpeer
    _('--max-peer', default=10, type=int,
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
        for id, ip, port, proto in peer_db.execute(
            "SELECT id, ip, port, proto FROM peers WHERE used = 0 ORDER BY RANDOM() LIMIT ?", (n,)):
            if config.verbose >= 2:
                print 'Establishing a connection with %s' % ip
            iface = free_interface_set.pop()
            connection_dict[id] = 
                    ( openvpn.client(ip, '--dev', iface, '--proto', proto, '--rport', str(port)) , iface)
            peer_db.execute("UPDATE peers SET used = 1 WHERE id = ?", (id,))
    except KeyError:
        if config.verbose >= 2:
            print "Can't establish connection with %s : no available interface" % ip
        pass
    except Exception:
        traceback.print_exc()

def killConnection(id):
    try:
        if config.verbose >= 2:
            print 'Killing the connection with ' + peer
        p, iface = connection_dict.pop(id)
        p.kill()
        free_interface_set.add(iface)
        peer_db.execute("UPDATE peers SET used = 0 WHERE id = ?", (id,))
    except KeyError:
        if config.verbose >= 1:
            print "Can't kill connection to " + peer + ": no existing connection"
        pass
    except Exception:
        if config.verbose >= 1:
            print "Can't kill connection to " + peer + ": uncaught error"
        pass


def refreshConnections():
    # Kill some random connections
    try:
        for i in range(0, int(config.refresh_count)):
            id = random.choice(connection_dict.keys())
            killConnection(id)
    except Exception:
        pass
    # Establish new connections
    startNewConnection(config.client_count - len(connection_dict))

def main():
    # Get arguments
    getConfig()
    (externalIp, externalPort) = upnpigd.GetExternalInfo(1194)

    # Setup database
    global peer_db # stop using global variables for everything ?
    peer_db = sqlite3.connect(config.db, isolation_level=None)
    peer_db.execute("""CREATE TABLE IF NOT EXISTS peers
             ( id INTEGER PRIMARY KEY AUTOINCREMENT,
             ip TEXT NOT NULL,
             port INTEGER NOT NULL,
             proto TEXT NOT NULL,
             used INTEGER NOT NULL)""")
    peer_db.execute("CREATE INDEX IF NOT EXISTS _peers_used ON peers(used)")
    peer_db.execute("UPDATE peers SET used = 0")

    # Establish connections
    serverProcess = openvpn.server(config.ip, '--dev', 'vifibnet')
    startNewConnection(config.client_count)

    # main loop
    try:
        while True:
            # TODO : use select to get openvpn events from pipes
            time.sleep(float(config.refresh_time))
            refreshConnections()
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    main()

# TODO : remove incomming connections from avalaible peers

