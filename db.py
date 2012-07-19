import sqlite3, xmlrpclib, time
import utils

class PeerManager:

    # internal ip = temp arg/attribute
    def __init__(self, db_path, server, server_port, refresh_time, address, internal_ip, prefix, manual, db_size):
        self._refresh_time = refresh_time
        self._address = address
        self._internal_ip = internal_ip
        self._prefix = prefix
        self._server = server
        self._server_port = server_port
        self._db_size = db_size
        self._manual = manual

        self._proxy = xmlrpclib.ServerProxy('http://%s:%u' % (server, server_port))

        utils.log('Connectiong to peers database', 4)
        self._db = sqlite3.connect(db_path, isolation_level=None)
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
        if self._address != None:
            utils.log('Sending connection info to server', 3)
            self._proxy.declare((self._internal_ip, utils.address_list(self._address)))
        else:
            utils.log("Warning : couldn't advertise to server, external config not known", 4)

    def _populate(self):
        utils.log('Populating the peers DB', 2)
        new_peer_list = self._proxy.getPeerList(self._db_size, self._internal_ip)
        self._db.executemany("INSERT OR IGNORE INTO peers (prefix, address) VALUES (?,?)", new_peer_list)
        self._db.execute("DELETE FROM peers WHERE prefix = ?", (self._prefix,))
        utils.log('New peers : %s' % ', '.join(map(str, new_peer_list)), 5)

    def getUnusedPeers(self, peer_count):
        return self._db.execute("""SELECT prefix, address FROM peers WHERE used = 0
                                   ORDER BY RANDOM() LIMIT ?""", (peer_count,))

    def usePeer(self, prefix):
        utils.log('Updating peers database : using peer ' + str(prefix), 5)
        self._db.execute("UPDATE peers SET used = 1 WHERE prefix = ?", (prefix,))

    def unusePeer(self, prefix):
        utils.log('Updating peers database : unusing peer ' + str(prefix), 5)
        self._db.execute("UPDATE peers SET used = 0 WHERE id = ?", (prefix,))

    def handle_message(self, msg):
        script_type, arg = msg.split()
        if script_type == 'client-connect':
            utils.log('Incomming connection from %s' % (arg,), 3)
        elif script_type == 'client-disconnect':
            utils.log('%s has disconnected' % (arg,), 3)
        elif script_type == 'route-up':
            if not self._manual:
                external_ip, external_port = arg.split(',')
                new_address = [[external_ip, external_port, 'udp'],
                                 [external_ip, external_port, 'tcp-client']]
                if self._address != new_address:
                    self._address = new_address
                    utils.log('Received new external configuration : %:%s' % (external_ip, external_port), 3)
                    self._declare()
        else:
            utils.log('Unknow message recieved from the openvpn pipe : ' + msg, 1)
