import logging, sqlite3, socket, subprocess, xmlrpclib, time, os
import utils

class PeerManager:

    # internal ip = temp arg/attribute
    def __init__(self, db_path, registry, key_path, refresh_time, address,
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

        logging.info('Connecting to peers database...')
        self._db = sqlite3.connect(db_path, isolation_level=None)
        logging.debug('Database opened')

        logging.info('Preparing peers database...')
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
        logging.debug('Database prepared')

        self.next_refresh = time.time()

    def clear_blacklist(self, flag):
        logging.info('Clearing blacklist from flag %u' % flag)
        self._db.execute("DELETE FROM blacklist WHERE flag = ?",
                          (flag,))
        logging.info('Blacklist cleared')

    def blacklist(self, prefix, flag):
        logging.ninfo('Blacklisting %s' % prefix)
        self._db.execute("DELETE FROM peers WHERE prefix = ?", (prefix,))
        self._db.execute("INSERT OR REPLACE INTO blacklist VALUES (?,?)",
                          (prefix, flag))
        logging.debug('%s blacklisted' % prefix)

    def whitelist(self, prefix):
        logging.info('Unblacklisting %s' % prefix)
        self._db.execute("DELETE FROM blacklist WHERE prefix = ?", (prefix,))
        logging.debug('%s whitelisted' % prefix)

    def refresh(self):
        logging.info('Refreshing the peers DB...')
        try:
            self._declare()
            self._populate()
            logging.info('DB refreshed')
            self.next_refresh = time.time() + self._refresh_time
            return True
        except socket.error, e:
            logging.debug('socket.error : %s' % e)
            logging.info('Connection to server failed, retrying in 30s')
            self.next_refresh = time.time() + 30
            return False

    def _declare(self):
        if self._address != None:
            logging.info('Sending connection info to server...')
            self._proxy.declare((self._internal_ip,
                    utils.address_str(self._address)))
            logging.debug('Info sent')
        else:
            logging.warning("Warning : couldn't send ip, unknown external config")

    def _populate(self):
        logging.info('Populating the peers DB...')
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
        logging.info('DB populated')
        logging.trace('New peers : %s' % (', '.join(map(str, new_peer_list)),))

    def getUnusedPeers(self, peer_count):
        for populate in self.refresh, self._bootstrap, bool:
            peer_list = self._db.execute("""SELECT prefix, address FROM peers WHERE used
                                            <= 0 ORDER BY used DESC,RANDOM() LIMIT ?""",
                                         (peer_count,)).fetchall()
            if peer_list or populate():
                return peer_list

    def _bootstrap(self):
        logging.info('Getting Boot peer...')
        proxy = xmlrpclib.ServerProxy(self._registry)
        try:
            bootpeer = proxy.getBootstrapPeer(self._prefix).data
            logging.debug('Boot peer received from server')
            p = subprocess.Popen(('openssl', 'rsautl', '-decrypt', '-inkey', self._key_path),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            bootpeer = p.communicate(bootpeer)[0].split()
            self._db.execute("INSERT INTO peers (prefix, address) VALUES (?,?)", bootpeer)
            logging.debug('Boot peer added')
            return True
        except socket.error:
            pass
        except sqlite3.IntegrityError, e:
            import pdb; pdb.set_trace()
            if e.args[0] != '':
                raise
        return False

    def usePeer(self, prefix):
        logging.trace('Updating peers database : using peer %s' % prefix)
        self._db.execute("UPDATE peers SET used = 1 WHERE prefix = ?",
                (prefix,))
        logging.debug('DB updated')

    def unusePeer(self, prefix):
        logging.trace('Updating peers database : unusing peer %s' % prefix)
        self._db.execute("UPDATE peers SET used = 0 WHERE prefix = ?",
                (prefix,))
        logging.debug('DB updated')

    def flagPeer(self, prefix):
        logging.trace('Updating peers database : flagging peer %s' % prefix)
        self._db.execute("UPDATE peers SET used = -1 WHERE prefix = ?",
                (prefix,))
        logging.debug('DB updated')

    def handle_message(self, msg):
        script_type, arg = msg.split()
        if script_type == 'client-connect':
            logging.info('Incomming connection from %s' % (arg,))
        elif script_type == 'client-disconnect':
            logging.info('%s has disconnected' % (arg,))
        elif script_type == 'route-up':
            if not self._manual:
                external_ip = arg
                new_address = list([external_ip, port, proto]
                                   for port, proto, _ in self._pp)
                if self._address != new_address:
                    self._address = new_address
                    logging.info('Received new external ip : %s'
                              % (external_ip,))
                    self._declare()
        else:
            logging.debug('Unknow message recieved from the openvpn pipe : %s'
                    % msg)

