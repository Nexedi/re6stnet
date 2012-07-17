from utils import *
import sqlite3
import xmlrpclib

class PeersDB:
    def __init__(self, dbPath):

        log('Connectiong to peers database', 4)
        self.db = sqlite3.connect(dbPath, isolation_level=None)
        log('Preparing peers database', 4)
        try:
            self.db.execute("UPDATE peers SET used = 0")
        except sqlite3.OperationalError, e:
            if e.args[0] == 'no such table: peers':
                raise RuntimeError

    def populate(self, n):
        # TODO: don't reconnect to server each time ?
        log('Connecting to remote server', 3)
        self.proxy = xmlrpclib.ServerProxy('http://%s:%u' % (config.server, config.server_port))
        log('Updating peers database : populating', 2)
        # TODO: determine port and proto
        port = 1194
        proto = 'udp'
        new_peer_list = self.proxy.getPeerList(n, (config.internal_ip, config.external_ip, port, proto))
        self.db.executemany("INSERT OR IGNORE INTO peers (ip, port, proto, used) VALUES (?,?,?,0)", new_peer_list)
        self.db.execute("DELETE FROM peers WHERE ip = ?", (config.external_ip,))

    def getUnusedPeers(self, nPeers):
        return self.db.execute("SELECT id, ip, port, proto FROM peers WHERE used = 0 "
                "ORDER BY RANDOM() LIMIT ?", (nPeers,))

    def usePeer(self, id):
        log('Updating peers database : using peer ' + str(id), 5)
        self.db.execute("UPDATE peers SET used = 1 WHERE id = ?", (id,))

    def unusePeer(self, id):
        log('Updating peers database : unusing peer ' + str(id), 5)
        self.db.execute("UPDATE peers SET used = 0 WHERE id = ?", (id,))
