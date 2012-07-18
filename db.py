#!/usr/bin/env python
import sqlite3, xmlrpclib, time
import utils

class PeerManager:

    def __init__(self, dbPath, server, server_port, refresh_time, external_ip, internal_ip, port, proto, db_size):
        self._server_port = server_port
        self._refresh_time = refresh_time
        self._external_ip = external_ip
        self._internal_ip = internal_ip
        self._external_port = port
        self._proto = proto
        self._db_size = db_size

        utils.log('Connectiong to peers database', 4)
        self._db = sqlite3.connect(dbPath, isolation_level=None)
        self._server = server
        utils.log('Preparing peers database', 4)
        try:
            self._db.execute("UPDATE peers SET used = 0")
        except sqlite3.OperationalError, e:
            if e.args[0] == 'no such table: peers':
                raise RuntimeError

        self.next_refresh = time.time()

    def refresh(self):
        self._populate()
        self.next_refresh = time.time() + self._refresh_time

    def _populate(self):
        if self._external_ip != None:
            address = (self._internal_ip, self._external_ip, self._external_port, self._proto)
        else:
            address = 0
        utils.log('Connecting to remote server', 3)
        self._proxy = xmlrpclib.ServerProxy('http://%s:%u' % (self._server, self._server_port))
        utils.log('Updating peers database : populating', 2)
        new_peer_list = self._proxy.getPeerList(self._db_size, address)
        utils.log('New peers recieved from %s' % self._server, 5)
        self._db.executemany("INSERT OR IGNORE INTO peers (ip, port, proto, used) VALUES (?,?,?,0)", new_peer_list)
        if self._external_ip != None:
            self._db.execute("DELETE FROM peers WHERE ip = ?", (self._external_ip,))
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
            self._external_ip = arg
        else:
            utils.log('Unknow message recieved from the openvpn pipe : ' + msg, 1)
