#!/usr/bin/env python
import sqlite3, xmlrpclib, time
import utils

class PeerManager:

    def __init__(self, dbPath, server, port, refresh_time):
        utils.log('Connectiong to peers database', 4)
        self._db = sqlite3.connect(dbPath, isolation_level=None)
        self._server = server
        self._port = port
        self._refresh_time = refresh_time
        utils.log('Preparing peers database', 4)
        try:
            self._db.execute("UPDATE peers SET used = 0")
        except sqlite3.OperationalError, e:
            if e.args[0] == 'no such table: peers':
                raise RuntimeError
        self.next_refresh = time.time()

    def populate(self, n, address):
        # address = (internal_ip, external_ip, port, proto)
        utils.log('Connecting to remote server', 3)
        self._proxy = xmlrpclib.ServerProxy('http://%s:%u' % (self._server, self._port))
        utils.log('Updating peers database : populating', 2)
        _, external_ip, _, _ = address
        new_peer_list = self._proxy.getPeerList(n, address)
        utils.log('New peers recieved from %s' % self._server, 5)
        self._db.executemany("INSERT OR IGNORE INTO peers (ip, port, proto, used) VALUES (?,?,?,0)", new_peer_list)
        self._db.execute("DELETE FROM peers WHERE ip = ?", (external_ip,))
        self.next_refresh = time.time() + self._refresh_time
        utils.log('New peers : %s' % ', '.join(map(str, new_peer_list)), 5)

    def getUnusedPeers(self, nPeers):
        return self._db.execute("SELECT id, ip, port, proto FROM peers WHERE used = 0 "
                "ORDER BY RANDOM() LIMIT ?", (nPeers,))

    def usePeer(self, id):
        utils.log('Updating peers database : using peer ' + str(id), 5)
        self._db.execute("UPDATE peers SET used = 1 WHERE id = ?", (id,))

    def unusePeer(self, id):
        utils.log('Updating peers database : unusing peer ' + str(id), 5)
        self._db.execute("UPDATE peers SET used = 0 WHERE id = ?", (id,))

    def handle_message(self, msg):
        script_type, arg = msg.split()
        if script_type == 'client-connect':
            utils.log('Incomming connection from %s' % (arg,), 3)
        elif script_type == 'client-disconnect':
            utils.log('%s has disconnected' % (arg,), 3)
        elif script_type == 'route-up':
            utils.log('External Ip : ' + arg, 3)
        else:
            utils.log('Unknow message recieved from the openvpn pipe : ' + msg, 1)
