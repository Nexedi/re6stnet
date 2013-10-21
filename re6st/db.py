import logging, sqlite3, socket, subprocess, time
from . import utils


class PeerDB(object):

    # internal ip = temp arg/attribute
    def __init__(self, db_path, registry, key_path, network, prefix,
                       db_size=200):
        self._prefix = prefix
        self._db_size = db_size
        self._key_path = key_path
        self._registry = registry

        logging.info('Initialize cache ...')
        self._db = sqlite3.connect(db_path, isolation_level=None)
        q = self._db.execute
        q("PRAGMA synchronous = OFF")
        q("PRAGMA journal_mode = MEMORY")
        q("""CREATE TABLE IF NOT EXISTS peer (
            prefix TEXT PRIMARY KEY,
            address TEXT NOT NULL)""")
        q("""CREATE TABLE IF NOT EXISTS config (
            name text primary key,
            value text)""")
        q('ATTACH DATABASE ":memory:" AS volatile')
        q("""CREATE TABLE volatile.stat (
            peer TEXT PRIMARY KEY,
            try INTEGER NOT NULL DEFAULT 0)""")
        q("CREATE INDEX volatile.stat_try ON stat(try)")
        q("INSERT INTO volatile.stat (peer) SELECT prefix FROM peer")
        try:
            a = q("SELECT value FROM config WHERE name='registry'").next()[0]
            int(a, 2)
        except (StopIteration, ValueError):
            logging.info("Asking registry its private IP...")
            retry = 1
            while True:
                try:
                    a = self._registry.getPrefix(self._prefix)
                    int(a, 2)
                    break
                except socket.error, e:
                    logging.warning(e)
                    time.sleep(retry)
                    retry = min(60, retry * 2)
            q("INSERT OR REPLACE INTO config VALUES ('registry',?)", (a,))
            self._db.commit()
        self.registry_prefix = a
        logging.info("Cache initialized. Prefix of registry node is %s/%u",
                     int(a, 2), len(a))

    def log(self):
        if logging.getLogger().isEnabledFor(5):
            logging.trace("Cache:")
            for prefix, address, _try in self._db.execute(
                    "SELECT peer.*, try FROM peer, volatile.stat"
                    " WHERE prefix=peer ORDER BY prefix"):
                logging.trace("- %s: %s%s", prefix, address,
                              ' (blacklisted)' if _try else '')

    def cacheMinimize(self, size):
        with self._db:
            self._cacheMinimize(size)

    def _cacheMinimize(self, size):
        a = self._db.execute(
            "SELECT peer FROM volatile.stat ORDER BY try, RANDOM() LIMIT ?,-1",
            (size,)).fetchall()
        if a:
            q = self._db.executemany
            q("DELETE FROM peer WHERE prefix IN (?)", a)
            q("DELETE FROM volatile.stat WHERE peer IN (?)", a)

    def connecting(self, prefix, connecting):
        self._db.execute("UPDATE volatile.stat SET try=? WHERE peer=?",
                         (connecting, prefix))

    def resetConnecting(self):
        self._db.execute("UPDATE volatile.stat SET try=0")

    def getAddress(self, prefix):
        r = self._db.execute("SELECT address FROM peer, volatile.stat"
                             " WHERE prefix=? AND prefix=peer AND try=0",
                             (prefix,)).fetchone()
        return r and r[0]

    # Exclude our own address from results in case it is there, which may
    # happen if a node change its certificate without clearing the cache.
    # IOW, one should probably always put our own address there.
    _get_peer_sql = "SELECT %s FROM peer, volatile.stat" \
                    " WHERE prefix=peer AND prefix!=? AND try=?"
    def getPeerList(self, failed=0, __sql=_get_peer_sql % "prefix, address"
                                                        + " ORDER BY RANDOM()"):
        return self._db.execute(__sql, (self._prefix, failed))
    def getPeerCount(self, failed=0, __sql=_get_peer_sql % "COUNT(*)"):
        return self._db.execute(__sql, (self._prefix, failed)).next()[0]

    def getBootstrapPeer(self):
        logging.info('Getting Boot peer...')
        try:
            bootpeer = self._registry.getBootstrapPeer(self._prefix)
            prefix, address = utils.decrypt(self._key_path, bootpeer).split()
        except (socket.error, subprocess.CalledProcessError, ValueError), e:
            logging.warning('Failed to bootstrap (%s)', e)
        else:
            if prefix != self._prefix:
                self.addPeer(prefix, address)
                return prefix, address
            logging.warning('Buggy registry sent us our own address')

    def addPeer(self, prefix, address, set_preferred=False):
        logging.debug('Adding peer %s: %s', prefix, address)
        with self._db:
            q = self._db.execute
            try:
                (a,), = q("SELECT address FROM peer WHERE prefix=?", (prefix,))
                if set_preferred:
                    preferred = address.split(';')
                    address = a
                else:
                    preferred = a.split(';')
                def key(a):
                    try:
                        return preferred.index(a)
                    except ValueError:
                        return len(preferred)
                address = ';'.join(sorted(address.split(';'), key=key))
            except ValueError:
                self._cacheMinimize(self._db_size)
                a = None
            if a != address:
                q("INSERT OR REPLACE INTO peer VALUES (?,?)", (prefix, address))
            q("INSERT OR REPLACE INTO volatile.stat VALUES (?,0)", (prefix,))
