import sqlite3, socket, subprocess, xmlrpclib, time, os
import utils

class PeerManager:

    # internal ip = temp arg/attribute
    def __init__(self, db_dir_path, registry, key_path, refresh_time, address,
                       internal_ip, prefix, manual, pp , db_size):
        self._refresh_time = refresh_time
        self._address = address
        self._internal_ip = internal_ip
        self._prefix = prefix
        self._db_size = db_size
        self._registry = registry
        self._key_path = key_path
        self._pp = pp
        self._manual = manual

        utils.log('Connectiong to peers database...', 4)
        self._db = sqlite3.connect(os.path.join(db_dir_path, 'peers.db'),
                                   isolation_level=None)
        utils.log('Database opened', 5)

        utils.log('Preparing peers database...', 4)
        self._db.execute("""CREATE TABLE IF NOT EXISTS peers (
                            prefix TEXT PRIMARY KEY,
                            address TEXT NOT NULL,
                            used INTEGER NOT NULL DEFAULT 0,
                            date INTEGER DEFAULT (strftime('%s', 'now')))""")
        self._db.execute("UPDATE peers SET used = 0")
        self._db.execute("CREATE INDEX IF NOT EXISTS _peers_used ON peers(used)")
        self._db.execute("""CREATE TABLE IF NOT EXISTS blacklist (
                            prefix TEXT PRIMARY KEY,
                            flag INTEGER NOT NULL)""")
        self._db.execute("""CREATE INDEX IF NOT EXISTS
                            blacklist_flag ON blacklist(flag)""")
        self._db.execute("INSERT OR REPLACE INTO blacklist VALUES (?,?)",
                         (prefix, 1))
        self._db.execute("""CREATE TABLE IF NOT EXISTS config (
                            name text primary key,
                            value text)""")
        try:
            a, = self._db.execute("SELECT value FROM config WHERE name='registry'").next()
        except StopIteration:
            proxy = xmlrpclib.ServerProxy(registry)
            a = proxy.getPrivateAddress()
            self._db.execute("INSERT INTO config VALUES ('registry',?)", (a,))
        self._proxy = xmlrpclib.ServerProxy(a)
        utils.log('Database prepared', 5)

        self.next_refresh = time.time()

    def clear_blacklist(self, flag):
        utils.log('Clearing blacklist from flag %u' % (flag,), 3)
        self._db.execute("DELETE FROM blacklist WHERE flag = ?",
                          (flag,))
        utils.log('Blacklist cleared', 5)

    def blacklist(self, prefix, flag):
        utils.log('Blacklisting %s' % (prefix,), 4)
        self._db.execute("DELETE FROM peers WHERE prefix = ?", (prefix,))
        self._db.execute("INSERT OR REPLACE INTO blacklist VALUES (?,?)",
                          (prefix, flag))
        utils.log('%s blacklisted' % (prefix,), 5)

    def whitelist(self, prefix):
        utils.log('Unblacklisting %s' % (prefix,), 4)
        self._db.execute("DELETE FROM blacklist WHERE prefix = ?", (prefix,))
        utils.log('%s whitelisted' % (prefix,), 5)

    def refresh(self):
        utils.log('Refreshing the peers DB...', 2)
        try:
            self._declare()
            self._populate()
            utils.log('DB refreshed', 3)
            self.next_refresh = time.time() + self._refresh_time
            return True
        except socket.error, e:
            utils.log(e, 4)
            utils.log('Connection to server failed, retrying in 30s', 2)
            self.next_refresh = time.time() + 30
            return False

    def _declare(self):
        if self._address != None:
            utils.log('Sending connection info to server...', 3)
            self._proxy.declare((self._internal_ip,
                    utils.address_str(self._address)))
            utils.log('Info sent', 5)
        else:
            utils.log("Warning : couldn't send ip, unknown external config", 4)

    def _populate(self):
        utils.log('Populating the peers DB...', 2)
        new_peer_list = self._proxy.getPeerList(self._db_size,
                self._internal_ip)
        with self._db:
            self._db.execute("""DELETE FROM peers WHERE used <= 0 ORDER BY used,
                                RANDOM() LIMIT MAX(0, ? + (SELECT COUNT(*)
                                FROM peers WHERE used <= 0))""",
                                (str(len(new_peer_list) - self._db_size),))
            self._db.executemany("""INSERT OR IGNORE INTO peers (prefix, address)
                                    VALUES (?,?)""", new_peer_list)
            self._db.execute("""DELETE FROM peers WHERE prefix IN
                                (SELECT prefix FROM blacklist)""")
        utils.log('DB populated', 3)
        utils.log('New peers : %s' % ', '.join(map(str, new_peer_list)), 5)

    def getUnusedPeers(self, peer_count):
        for populate in self.refresh, self._bootstrap, bool:
            peer_list = self._db.execute("""SELECT prefix, address FROM peers WHERE used
                                            <= 0 ORDER BY used DESC,RANDOM() LIMIT ?""",
                                         (peer_count,)).fetchall()
            if peer_list or populate():
                return peer_list

    def _bootstrap(self):
        utils.log('Getting Boot peer...', 3)
        proxy = xmlrpclib.ServerProxy(self._registry)
        try:
            bootpeer = proxy.getBootstrapPeer(self._prefix).data
            utils.log('Boot peer received from server', 4)
            p = subprocess.Popen(('openssl', 'rsautl', '-decrypt', '-inkey', self._key_path),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            bootpeer = p.communicate(bootpeer).split()
            self.db.execute("INSERT INTO peers (prefix, address) VALUES (?,?)", bootpeer)
            utils.log('Boot peer added', 4)
            return True
        except socket.error:
            pass
        except sqlite3.IntegrityError, e:
            import pdb; pdb.set_trace()
            if e.args[0] != '':
                raise
        return False

    def usePeer(self, prefix):
        utils.log('Updating peers database : using peer ' + str(prefix), 5)
        self._db.execute("UPDATE peers SET used = 1 WHERE prefix = ?", 
                (prefix,))
        utils.log('DB updated', 5)

    def unusePeer(self, prefix):
        utils.log('Updating peers database : unusing peer ' + str(prefix), 5)
        self._db.execute("UPDATE peers SET used = 0 WHERE prefix = ?", 
                (prefix,))
        utils.log('DB updated', 5)

    def flagPeer(self, prefix):
        utils.log('Updating peers database : flagging peer ' + str(prefix), 5)
        self._db.execute("UPDATE peers SET used = -1 WHERE prefix = ?",
                (prefix,))
        utils.log('DB updated', 5)

    def handle_message(self, msg):
        script_type, arg = msg.split()
        if script_type == 'client-connect':
            utils.log('Incomming connection from %s' % (arg,), 3)
        elif script_type == 'client-disconnect':
            utils.log('%s has disconnected' % (arg,), 3)
        elif script_type == 'route-up':
            if not self._manual:
                external_ip = arg
                new_address = list([external_ip, port, proto]
                                   for port, proto in self._pp)
                if self._address != new_address:
                    self._address = new_address
                    utils.log('Received new external ip : %s' 
                              % (external_ip,), 3)
                    self._declare()
        else:
            utils.log('Unknow message recieved from the openvpn pipe : '
                    + msg, 1)

