import sqlite3, xmlrpclib, time
import utils

class PeerManager:

    def __init__(self, dbPath, server, server_port, refresh_time, external_ip, internal_ip, port, proto, db_size):
        self._refresh_time = refresh_time
        self._external_ip = external_ip
        self._internal_ip = internal_ip
        self._external_port = port
        self._proto = proto
        self._db_size = db_size
        self._proxy = xmlrpclib.ServerProxy('http://%s:%u' % (server, server_port))

        utils.log('Connectiong to peers database', 4)
        self._db = sqlite3.connect(dbPath, isolation_level=None)
        utils.log('Preparing peers database', 4)
        try:
            self._db.execute("UPDATE peers SET used = 0")
        except sqlite3.OperationalError, e:
            if e.args[0] == 'no such table: peers':
                raise RuntimeError

        self.next_refresh = time.time()

    def refresh(self):
        utils.log('Refreshing the peers DB', 2)
        self._declare()
        self._populate()
        self.next_refresh = time.time() + self._refresh_time

    def _declare(self):
        if self._external_ip != None:
            utils.log('Declaring our connections info', 3)
            self._proxy.declare((self._internal_ip, self._external_ip, self._external_port, self._proto))
        else:
            utils.log('Warning : could not declare the external ip because it is unknown', 4)

    def _populate(self):
        utils.log('Populating the peers DB', 2)
        new_peer_list = self._proxy.getPeerList(self._db_size, self._internal_ip)
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
            if arg != self._external_ip:
                self._external_ip = arg
                utils.log('External Ip : ' + arg, 3)
                self._declare()
        else:
            utils.log('Unknow message recieved from the openvpn pipe : ' + msg, 1)
