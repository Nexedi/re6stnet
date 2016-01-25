import json, logging, os, sqlite3, socket, subprocess, sys, time, zlib
from .registry import RegistryClient
from . import utils, version, x509

class Cache(object):

    crl = ()

    def __init__(self, db_path, registry, cert, db_size=200):
        self._prefix = cert.prefix
        self._db_size = db_size
        self._decrypt = cert.decrypt
        self._registry = RegistryClient(registry, cert)

        logging.info('Initialize cache ...')
        try:
            self._db = self._open(db_path)
        except sqlite3.OperationalError:
            logging.exception("Start with empty cache")
            os.rename(db_path, db_path + '.bak')
            self._db = self._open(db_path)
        q = self._db.execute
        q('ATTACH DATABASE ":memory:" AS volatile')
        q("""CREATE TABLE volatile.stat (
            peer TEXT PRIMARY KEY NOT NULL,
            try INTEGER NOT NULL DEFAULT 0)""")
        q("CREATE INDEX volatile.stat_try ON stat(try)")
        q("INSERT INTO volatile.stat (peer) SELECT prefix FROM peer")
        self._db.commit()
        self._loadConfig(self._selectConfig(q))
        try:
            cert.verifyVersion(self.version)
        except (AttributeError, x509.VerifyError):
            retry = 1
            while not self.updateConfig():
                time.sleep(retry)
                retry = min(60, retry * 2)
        else:
            if (# re6stnet upgraded after being unused  for a long time.
                self.protocol < version.protocol
                # Always query the registry at startup in case we were down
                # when it tried to send us new parameters.
                or self._prefix == self.registry_prefix):
                self.updateConfig()
        self.next_renew = cert.maybeRenew(self._registry, self.crl)
        if version.protocol < self.min_protocol:
            logging.critical("Your version of re6stnet is too old."
                             " Please update.")
            sys.exit(1)
        self.warnProtocol()
        logging.info("Cache initialized.")

    def _open(self, path):
        db = sqlite3.connect(path, isolation_level=None)
        db.text_factory = str
        db.execute("PRAGMA synchronous = OFF")
        db.execute("PRAGMA journal_mode = MEMORY")
        utils.sqliteCreateTable(db, "peer",
            "prefix TEXT PRIMARY KEY NOT NULL",
            "address TEXT NOT NULL")
        utils.sqliteCreateTable(db, "config",
            "name TEXT PRIMARY KEY NOT NULL",
            "value")
        return db

    @staticmethod
    def _selectConfig(execute): # BBB: blob
        return ((k, str(v) if type(v) is buffer else v)
            for k, v in execute("SELECT * FROM config"))

    def _loadConfig(self, config):
        cls = self.__class__
        logging.debug("Loading network parameters:")
        for k, v in config:
            if k == 'crl':
                v = set(json.loads(v))
            elif hasattr(cls, k):
                continue
            setattr(self, k, v)
            logging.debug("- %s: %r", k, v)

    def updateConfig(self):
        logging.info("Getting new network parameters from registry...")
        try:
            # TODO: When possible, the registry should be queried via the re6st.
            config = json.loads(zlib.decompress(
                self._registry.getNetworkConfig(self._prefix)))
            base64 = config.pop('', ())
            config = dict((str(k), v.decode('base64') if k in base64 else
                                   str(v) if type(v) is unicode else v)
                          for k, v in config.iteritems())
            config['crl'] = json.dumps(config['crl'])
        except socket.error, e:
            logging.warning(e)
            return
        except Exception:
            # Even if the response is authenticated, a mistake on the registry
            # should not kill the whole network in a few seconds.
            logging.exception("buggy registry ?")
            return
        # XXX: check version ?
        self.delay_restart = config.pop("delay_restart", 0)
        old = {}
        with self._db as db:
            remove = []
            for k, v in self._selectConfig(db.execute):
                if k in config:
                    old[k] = v
                    continue
                try:
                    delattr(self, k)
                except AttributeError:
                    pass
                remove.append(k)
            db.execute("DELETE FROM config WHERE name in ('%s')"
                       % "','".join(remove))
            # BBB: Use buffer because of http://bugs.python.org/issue13676
            #      on Python 2.6
            db.executemany("INSERT OR REPLACE INTO config VALUES(?,?)",
                           ((k, buffer(v) if k in base64 else v)
                            for k, v in config.iteritems()))
        self._loadConfig(config.iteritems())
        return [k for k, v in config.iteritems()
                  if k not in old or old[k] != v]

    def warnProtocol(self):
        if version.protocol < self.protocol:
            logging.warning("There's a new version of re6stnet:"
                            " you should update.")

    def getDh(self, path):
        # We'd like to do a full check here but
        #   from OpenSSL import SSL
        #   SSL.Context(SSL.TLSv1_METHOD).load_tmp_dh(path)
        # segfaults if file is corrupted.
        if not os.path.exists(path):
            retry = 1
            while True:
                try:
                    dh = self._registry.getDh(self._prefix)
                    if dh:
                        break
                    e = None
                except socket.error:
                    e = sys.exc_info()
                logging.warning(
                    "Failed to get DH parameters from the registry."
                    " Will retry in %s seconds", retry, exc_info=e)
                time.sleep(retry)
                retry = min(60, retry * 2)
            with open(path, "wb") as f:
                f.write(dh)

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
            prefix, address = self._decrypt(bootpeer).split()
        except (socket.error, subprocess.CalledProcessError, ValueError), e:
            logging.warning('Failed to bootstrap (%s)',
                            e if bootpeer else 'no peer returned')
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
