"""
Authenticated communication:

  handshake (hello):
    C->S: CN
    S->C: X = Encrypt(CN)(secret), Sign(CA)(X)

  call:
    C->S: CN, ..., HMAC(secret+1)(path_info?query_string)
    S->C: result, HMAC(secret+2)(result)

  secret+1 = SHA1(secret) to protect from replay attacks

  HMAC in custom header, base64-encoded

  To prevent anyone from breaking an existing session,
  keep 2 secrets for each client:
  - the last one that was really used by the client (!hello)
  - the one of the last handshake (hello)
"""
import base64, hmac, hashlib, httplib, inspect, json, logging
import mailbox, os, random, select, smtplib, socket, sqlite3
import string, struct, sys, threading, time, weakref, zlib
from collections import defaultdict, deque
from datetime import datetime
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from email.mime.text import MIMEText
from operator import itemgetter
from OpenSSL import crypto
from urllib import splittype, splithost, unquote, urlencode
from . import ctl, tunnel, utils, version, x509

HMAC_HEADER = "Re6stHMAC"
RENEW_PERIOD = 30 * 86400
GRACE_PERIOD = 100 * 86400

def rpc(f):
    args, varargs, varkw, defaults = inspect.getargspec(f)
    assert not (varargs or varkw or defaults), f
    f.getcallargs = eval("lambda %s: locals()" % ','.join(args[1:]))
    return f


class HTTPError(Exception):
    pass


class RegistryServer(object):

    peers = 0, ()
    cert_duration = 365 * 86400

    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.sessions = {}
        self.sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)

        # Database initializing
        db_dir = os.path.dirname(self.config.db)
        db_dir and utils.makedirs(db_dir)
        self.db = sqlite3.connect(self.config.db, isolation_level=None,
                                                  check_same_thread=False)
        self.db.text_factory = str
        utils.sqliteCreateTable(self.db, "config",
                "name TEXT PRIMARY KEY NOT NULL",
                "value")
        self.prefix = self.getConfig("prefix", None)
        self.version = str(self.getConfig("version", "\0")) # BBB: blob
        utils.sqliteCreateTable(self.db, "token",
                "token TEXT PRIMARY KEY NOT NULL",
                "email TEXT NOT NULL",
                "prefix_len INTEGER NOT NULL",
                "date INTEGER NOT NULL")
        if utils.sqliteCreateTable(self.db, "cert",
                "prefix TEXT PRIMARY KEY NOT NULL",
                "email TEXT",
                "cert TEXT"):
            self.db.execute("INSERT INTO cert VALUES ('',null,null)")
        utils.sqliteCreateTable(self.db, "crl",
                "serial INTEGER PRIMARY KEY NOT NULL",
                # Expiration date of revoked certificate.
                # TODO: purge rows with dates in the past.
                "date INTEGER NOT NULL")

        self.cert = x509.Cert(self.config.ca, self.config.key)
        # Get vpn network prefix
        self.network = self.cert.network
        logging.info("Network: %s/%u", utils.ipFromBin(self.network),
                                       len(self.network))
        self.email = self.cert.ca.get_subject().emailAddress

        self.peers_lock = threading.Lock()
        self.ctl = ctl.Babel(os.path.join(config.run, 'babeld.sock'),
            weakref.proxy(self), self.network)

        self.onTimeout()
        if self.prefix:
            with self.db:
                self.updateNetworkConfig()

    def getConfig(self, name, *default):
        r, = next(self.db.execute(
            "SELECT value FROM config WHERE name=?", (name,)), default)
        return r

    def setConfig(self, *name_value):
        self.db.execute("INSERT OR REPLACE INTO config VALUES (?, ?)",
                        name_value)

    def updateNetworkConfig(self, _it0=itemgetter(0)):
        kw = {
            'babel_default': 'max-rtt-penalty 5000 rtt-max 500 rtt-decay 125',
            'crl': map(_it0, self.db.execute(
                "SELECT serial FROM crl ORDER BY serial")),
            'protocol': version.protocol,
            'registry_prefix': self.prefix,
        }
        if self.config.ipv4:
            kw['ipv4'], kw['ipv4_sublen'] = self.config.ipv4
        for x in ('client_count', 'encrypt', 'hello',
                  'max_clients', 'min_protocol', 'tunnel_refresh'):
            kw[x] = getattr(self.config, x)
        config = json.dumps(kw, sort_keys=True)
        if config != self.getConfig('last_config', None):
            self.version = self.encodeVersion(
                1 + self.decodeVersion(self.version))
            # BBB: Use buffer because of http://bugs.python.org/issue13676
            #      on Python 2.6
            self.setConfig('version', buffer(self.version))
            self.setConfig('last_config', config)
            self.sendto(self.prefix, 0)
        kw[''] = 'version',
        # Example to avoid all nodes to restart at the same time:
        # kw['delay_restart'] = 600 * random.random()
        kw['version'] = self.version.encode('base64')
        self.network_config = zlib.compress(json.dumps(kw))

    # The 3 first bits code the number of bytes.
    def encodeVersion(self, version):
        for n in xrange(8):
            x = 32 << 8 * n
            if version < x:
                x = struct.pack("!Q", version + n * x)[7-n:]
                return x + self.cert.sign(x)
            version -= x

    def decodeVersion(self, version):
        n = ord(version[0]) >> 5
        version, = struct.unpack("!Q", '\0' * (7 - n) + version[:n+1])
        return sum((32 << 8 * n for n in xrange(n)),
                   version - (n * 32 << 8 * n))

    def sendto(self, prefix, code):
        self.sock.sendto("%s\0%c" % (prefix, code), ('::1', tunnel.PORT))

    def recv(self, code):
        try:
            prefix, msg = self.sock.recv(1<<16).split('\0', 1)
            int(prefix, 2)
        except ValueError:
            pass
        else:
            if msg and ord(msg[0]) == code:
                return prefix, msg[1:]
        return None, None

    def select(self, r, w, t):
        if self.timeout:
            t.append((self.timeout, self.onTimeout))

    def request_dump(self):
        assert self.peers_lock.locked()
        def abort():
            raise ctl.BabelException
        self._wait_dump = True
        for _ in 0, 1:
            self.ctl.request_dump()
            try:
                while self._wait_dump:
                    args = {}, {}, ((time.time() + 5, abort),)
                    self.ctl.select(*args)
                    utils.select(*args)
                break
            except ctl.BabelException:
                self.ctl.reset()

    def babel_dump(self):
        self._wait_dump = False

    def iterCert(self):
        for prefix, email, cert in self.db.execute(
                "SELECT * FROM cert WHERE cert IS NOT NULL"):
            try:
                yield (crypto.load_certificate(crypto.FILETYPE_PEM, cert),
                       prefix, email)
            except crypto.Error:
                pass

    def onTimeout(self):
        # XXX: Because we use threads to process requests, the statements
        #      'self.timeout = 1' below have no effect as long as the
        #      'select' call does not return. Ideally, we should interrupt it.
        logging.info("Checking if there's any old entry in the database ...")
        not_after = None
        old = time.time() - GRACE_PERIOD
        q =  self.db.execute
        with self.lock:
          with self.db:
            q("BEGIN")
            for token, x in q("SELECT token, date FROM token"):
                if x <= old:
                    q("DELETE FROM token WHERE token=?", (token,))
                elif not_after is None or x < not_after:
                    not_after = x
            for cert, prefix, email in self.iterCert():
                x = x509.notAfter(cert)
                if x <= old:
                    if prefix == self.prefix:
                        logging.critical("Refuse to delete certificate"
                                         " of main node: wrong clock ?")
                        sys.exit(1)
                    logging.info("Delete %s: %s (invalid since %s)",
                        "certificate requested by '%s'" % email
                        if email else "anonymous certificate",
                        ", ".join("%s=%s" % x for x in
                                  cert.get_subject().get_components()),
                        datetime.utcfromtimestamp(x).isoformat())
                    q("UPDATE cert SET email=null, cert=null WHERE prefix=?",
                      (prefix,))
                elif not_after is None or x < not_after:
                    not_after = x
            # TODO: reduce 'cert' table by merging free slots
            #       (IOW, do the contrary of newPrefix)
            self.timeout = not_after and not_after + GRACE_PERIOD

    def handle_request(self, request, method, kw,
                       _localhost=('127.0.0.1', '::1')):
        m = getattr(self, method)
        if method in ('revoke', 'versions', 'topology'):
            x_forwarded_for = request.headers.get('X-Forwarded-For')
            if request.client_address[0] not in _localhost or \
               x_forwarded_for and x_forwarded_for not in _localhost:
                return request.send_error(httplib.FORBIDDEN)
        key = m.getcallargs(**kw).get('cn')
        if key:
            h = base64.b64decode(request.headers[HMAC_HEADER])
            with self.lock:
                session = self.sessions[key]
                for key in session:
                    if h == hmac.HMAC(key, request.path, hashlib.sha1).digest():
                        break
                else:
                    raise Exception("Wrong HMAC")
                key = hashlib.sha1(key).digest()
                session[:] = hashlib.sha1(key).digest(),
        try:
            result = m(**kw)
        except HTTPError, e:
            return request.send_error(*e.args)
        except:
            logging.warning(request.requestline, exc_info=1)
            return request.send_error(httplib.INTERNAL_SERVER_ERROR)
        if result:
            request.send_response(httplib.OK)
            request.send_header("Content-Length", str(len(result)))
        else:
            request.send_response(httplib.NO_CONTENT)
        if key:
            request.send_header(HMAC_HEADER, base64.b64encode(
                hmac.HMAC(key, result, hashlib.sha1).digest()))
        request.end_headers()
        if result:
            request.wfile.write(result)

    @rpc
    def hello(self, client_prefix):
        with self.lock:
            cert = self.getCert(client_prefix)
            key = utils.newHmacSecret()
            self.sessions.setdefault(client_prefix, [])[1:] = key,
        key = x509.encrypt(cert, key)
        sign = self.cert.sign(key)
        assert len(key) == len(sign)
        return key + sign

    def getCert(self, client_prefix):
        assert self.lock.locked()
        return self.db.execute("SELECT cert FROM cert"
                               " WHERE prefix=? AND cert IS NOT NULL",
                               (client_prefix,)).next()[0]

    @rpc
    def requestToken(self, email):
        prefix_len = self.config.prefix_length
        if not prefix_len:
            raise HTTPError(httplib.FORBIDDEN)
        with self.lock:
            while True:
                # Generating token
                token = ''.join(random.sample(string.ascii_lowercase, 8))
                args = token, email, prefix_len, int(time.time())
                # Updating database
                try:
                    self.db.execute("INSERT INTO token VALUES (?,?,?,?)", args)
                    break
                except sqlite3.IntegrityError:
                    pass
            self.timeout = 1

        # Creating and sending email
        msg = MIMEText('Hello, your token to join re6st network is: %s\n'
                       % token)
        msg['Subject'] = '[re6stnet] Token Request'
        if self.email:
            msg['From'] = self.email
        msg['To'] = email
        if os.path.isabs(self.config.mailhost) or \
           os.path.isfile(self.config.mailhost):
            with self.lock:
                m = mailbox.mbox(self.config.mailhost)
                try:
                    m.add(msg)
                finally:
                    m.close()
        else:
            s = smtplib.SMTP(self.config.mailhost)
            s.sendmail(self.email, email, msg.as_string())
            s.quit()

    def newPrefix(self, prefix_len):
        max_len = 128 - len(self.network)
        assert 0 < prefix_len <= max_len
        try:
            prefix, = self.db.execute("""SELECT prefix FROM cert WHERE length(prefix) <= ? AND cert is null
                                         ORDER BY length(prefix) DESC""", (prefix_len,)).next()
        except StopIteration:
            logging.error('No more free /%u prefix available', prefix_len)
            raise
        while len(prefix) < prefix_len:
            self.db.execute("UPDATE cert SET prefix = ? WHERE prefix = ?", (prefix + '1', prefix))
            prefix += '0'
            self.db.execute("INSERT INTO cert VALUES (?,null,null)", (prefix,))
        if len(prefix) < max_len or '1' in prefix:
            return prefix
        self.db.execute("UPDATE cert SET cert = 'reserved' WHERE prefix = ?", (prefix,))
        return self.newPrefix(prefix_len)

    @rpc
    def requestCertificate(self, token, req):
        req = crypto.load_certificate_request(crypto.FILETYPE_PEM, req)
        with self.lock:
            with self.db:
                if token:
                    if not self.config.prefix_length:
                        raise HTTPError(httplib.FORBIDDEN)
                    try:
                        token, email, prefix_len, _ = self.db.execute(
                            "SELECT * FROM token WHERE token = ?",
                            (token,)).next()
                    except StopIteration:
                        return
                    self.db.execute("DELETE FROM token WHERE token = ?",
                                    (token,))
                else:
                    prefix_len = self.config.anonymous_prefix_length
                    if not prefix_len:
                        raise HTTPError(httplib.FORBIDDEN)
                    email = None
                prefix = self.newPrefix(prefix_len)
                self.db.execute("UPDATE cert SET email = ? WHERE prefix = ?",
                                (email, prefix))
                if self.prefix is None:
                    self.prefix = prefix
                    self.setConfig('prefix', prefix)
                    self.updateNetworkConfig()
                subject = req.get_subject()
                subject.serialNumber = str(self.getSubjectSerial())
                return self.createCertificate(prefix, subject, req.get_pubkey())

    def getSubjectSerial(self):
        # Smallest unique number, for IPv4 support.
        serials = []
        for x in self.iterCert():
            serial = x[0].get_subject().serialNumber
            if serial:
                serials.append(int(serial))
        serials.sort()
        for serial, x in enumerate(serials):
            if serial != x:
                return serial
        return len(serials)

    def createCertificate(self, client_prefix, subject, pubkey, not_after=None):
        cert = crypto.X509()
        cert.gmtime_adj_notBefore(0)
        if not_after:
            cert.set_notAfter(not_after)
        else:
            cert.gmtime_adj_notAfter(self.cert_duration)
        cert.set_issuer(self.cert.ca.get_subject())
        subject.CN = "%u/%u" % (int(client_prefix, 2), len(client_prefix))
        cert.set_subject(subject)
        cert.set_pubkey(pubkey)
        # Certificate serial, for revocation support. Contrary to
        # subject serial, it does not need to be as small as possible.
        serial = 1 + self.getConfig('serial', 0)
        self.setConfig('serial', serial)
        cert.set_serial_number(serial)
        cert.sign(self.cert.key, 'sha512')
        cert = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)
        self.db.execute("UPDATE cert SET cert = ? WHERE prefix = ?",
                        (cert, client_prefix))
        self.timeout = 1
        return cert

    @rpc
    def renewCertificate(self, cn):
        with self.lock:
            with self.db as db:
                pem = self.getCert(cn)
                cert = crypto.load_certificate(crypto.FILETYPE_PEM, pem)
                if x509.notAfter(cert) - RENEW_PERIOD < time.time():
                    not_after = None
                elif db.execute("SELECT count(*) FROM crl WHERE serial=?",
                                (cert.get_serial_number(),)).fetchone()[0]:
                    not_after = cert.get_notAfter()
                else:
                    return pem
                return self.createCertificate(cn,
                    cert.get_subject(), cert.get_pubkey(), not_after)

    @rpc
    def getCa(self):
        return crypto.dump_certificate(crypto.FILETYPE_PEM, self.cert.ca)

    @rpc
    def getDh(self, cn):
        with open(self.config.dh) as f:
            return f.read()

    @rpc
    def getNetworkConfig(self, cn):
        return self.network_config

    @rpc
    def getBootstrapPeer(self, cn):
        with self.peers_lock:
            age, peers = self.peers
            if age < time.time() or not peers:
                self.request_dump()
                peers = [prefix
                    for neigh_routes in self.ctl.neighbours.itervalues()
                    for prefix in neigh_routes[1]
                    if prefix]
                peers.append(self.prefix)
                random.shuffle(peers)
                self.peers = time.time() + 60, peers
            peer = peers.pop()
            if peer == cn:
                # Very unlikely (e.g. peer restarted with empty cache),
                # so don't bother looping over above code
                # (in case 'peers' is empty).
                peer = self.prefix
        with self.lock:
            self.sendto(peer, 1)
            s = self.sock,
            timeout = 3
            end = timeout + time.time()
            # Loop because there may be answers from previous requests.
            while select.select(s, (), (), timeout)[0]:
                prefix, msg = self.recv(1)
                if prefix == peer:
                    break
                timeout = max(0, end - time.time())
            else:
                logging.info("Timeout while querying address for %s/%s",
                             int(peer, 2), len(peer))
                return
            cert = self.getCert(cn)
        msg = "%s %s" % (peer, msg)
        logging.info("Sending bootstrap peer: %s", msg)
        return x509.encrypt(cert, msg)

    @rpc
    def revoke(self, cn_or_serial):
        with self.lock:
          with self.db:
            q = self.db.execute
            try:
                serial = int(cn_or_serial)
            except ValueError:
                prefix = utils.binFromSubnet(cn_or_serial)
                cert = self.getCert(prefix)
                q("UPDATE cert SET email=null, cert=null WHERE prefix=?",
                  (prefix,))
                cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert)
                serial = cert.get_serial_number()
                self.sessions.pop(prefix, None)
            else:
                cert, = (cert for cert, prefix, email in self.iterCert()
                              if cert.get_serial_number() == serial)
            not_after = x509.notAfter(cert)
            if time.time() < not_after:
                q("INSERT INTO crl VALUES (?,?)", (serial, not_after))
                self.updateNetworkConfig()

    @rpc
    def versions(self):
        with self.peers_lock:
            self.request_dump()
            peers = set(prefix
                for neigh_routes in self.ctl.neighbours.itervalues()
                for prefix in neigh_routes[1]
                if prefix)
        peers.add(self.prefix)
        peer_dict = {}
        s = self.sock,
        with self.lock:
            while True:
                r, w, _ = select.select(s, s if peers else (), (), 3)
                if r:
                    prefix, ver = self.recv(4)
                    if prefix:
                        peer_dict[prefix] = ver
                if w:
                    prefix = peers.pop()
                    peer_dict[prefix] = None
                    self.sendto(prefix, 4)
                elif not r:
                    break
        return json.dumps(peer_dict)

    @rpc
    def topology(self):
        p = lambda p: '%s/%s' % (int(p, 2), len(p))
        peers = deque((p(self.prefix),))
        graph = defaultdict(set)
        s = self.sock,
        with self.lock:
            while True:
                r, w, _ = select.select(s, s if peers else (), (), 3)
                if r:
                    prefix, x = self.recv(5)
                    if prefix and x:
                        prefix = p(prefix)
                        x = x.split()
                        try:
                            n = int(x.pop(0))
                        except ValueError:
                            continue
                        if n <= len(x) and prefix not in x:
                            graph[prefix].update(x[:n])
                            peers += set(x).difference(graph)
                            for x in x[n:]:
                                graph[x].add(prefix)
                            graph[''].add(prefix)
                if w:
                    self.sendto(utils.binFromSubnet(peers.popleft()), 5)
                elif not r:
                    break
        return json.dumps(dict((k, list(v)) for k, v in graph.iteritems()))


class RegistryClient(object):

    _hmac = None
    user_agent = "re6stnet/" + version.version

    def __init__(self, url, cert=None, auto_close=True):
        self.cert = cert
        self.auto_close = auto_close
        scheme, host = splittype(url)
        host, path = splithost(host)
        self._conn = dict(http=httplib.HTTPConnection,
                          https=httplib.HTTPSConnection,
                          )[scheme](unquote(host), timeout=60)
        self._path = path.rstrip('/')

    def __getattr__(self, name):
        getcallargs = getattr(RegistryServer, name).getcallargs
        def rpc(*args, **kw):
            kw = getcallargs(*args, **kw)
            query = '/' + name
            if kw:
                if any(type(v) is not str for v in kw.itervalues()):
                    raise TypeError
                query += '?' + urlencode(kw)
            url = self._path + query
            client_prefix = kw.get('cn')
            retry = True
            try:
                while retry:
                    if client_prefix:
                        key = self._hmac
                        if not key:
                            retry = False
                            h = self.hello(client_prefix)
                            n = len(h) // 2
                            self.cert.verify(h[n:], h[:n])
                            key = self.cert.decrypt(h[:n])
                        h = hmac.HMAC(key, query, hashlib.sha1).digest()
                        key = hashlib.sha1(key).digest()
                        self._hmac = hashlib.sha1(key).digest()
                    else:
                        retry = False
                    self._conn.putrequest('GET', url, skip_accept_encoding=1)
                    self._conn.putheader('User-Agent', self.user_agent)
                    if client_prefix:
                        self._conn.putheader(HMAC_HEADER, base64.b64encode(h))
                    self._conn.endheaders()
                    response = self._conn.getresponse()
                    body = response.read()
                    if response.status in (httplib.OK, httplib.NO_CONTENT):
                        if (not client_prefix or
                                hmac.HMAC(key, body, hashlib.sha1).digest() ==
                                base64.b64decode(response.msg[HMAC_HEADER])):
                            if self.auto_close and name != 'hello':
                                self._conn.close()
                            return body
                    elif response.status == httplib.FORBIDDEN:
                        # XXX: We should improve error handling, while making
                        #      sure re6st nodes don't crash on temporary errors.
                        #      This is currently good enough for re6st-conf, to
                        #      inform the user when registration is disabled.
                        raise HTTPError(response.status, response.reason)
                    if client_prefix:
                        self._hmac = None
            except HTTPError:
                raise
            except Exception:
                logging.info(url, exc_info=1)
            else:
                logging.info('%s\nUnexpected response %s %s',
                             url, response.status, response.reason)
            self._conn.close()
        setattr(self, name, rpc)
        return rpc
