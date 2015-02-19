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
import base64, hmac, hashlib, httplib, inspect, logging
import mailbox, os, random, select, smtplib, socket, sqlite3
import string, struct, sys, threading, time, weakref
from collections import deque
from datetime import datetime
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from email.mime.text import MIMEText
from OpenSSL import crypto
from urllib import splittype, splithost, splitport, urlencode
from . import ctl, tunnel, utils, version

HMAC_HEADER = "Re6stHMAC"
RENEW_PERIOD = 30 * 86400
GRACE_PERIOD = 100 * 86400

def rpc(f):
    args, varargs, varkw, defaults = inspect.getargspec(f)
    assert not (varargs or varkw or defaults), f
    f.getcallargs = eval("lambda %s: locals()" % ','.join(args[1:]))
    return f


class RegistryServer(object):

    peers = 0, ()
    cert_duration = 365 * 86400

    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.sessions = {}
        self.sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)

        # Database initializing
        utils.makedirs(os.path.dirname(self.config.db))
        self.db = sqlite3.connect(self.config.db, isolation_level=None,
                                                  check_same_thread=False)
        self.db.execute("""CREATE TABLE IF NOT EXISTS config (
                        name text primary key,
                        value text)""")
        try:
            (self.prefix,), = self.db.execute(
                "SELECT value FROM config WHERE name='prefix'")
        except ValueError:
            self.prefix = None
        self.db.execute("""CREATE TABLE IF NOT EXISTS token (
                        token text primary key not null,
                        email text not null,
                        prefix_len integer not null,
                        date integer not null)""")
        try:
            self.db.execute("""CREATE TABLE cert (
                               prefix text primary key not null,
                               email text,
                               cert text)""")
        except sqlite3.OperationalError, e:
            if e.args[0] != 'table cert already exists':
                raise RuntimeError
        else:
            self.db.execute("INSERT INTO cert VALUES ('',null,null)")

        # Loading certificates
        with open(self.config.ca) as f:
            self.ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        with open(self.config.key) as f:
            self.key = crypto.load_privatekey(crypto.FILETYPE_PEM, f.read())
        # Get vpn network prefix
        self.network = utils.networkFromCa(self.ca)
        logging.info("Network: %s/%u", utils.ipFromBin(self.network),
                                       len(self.network))
        self.email = self.ca.get_subject().emailAddress

        self.peers_lock = threading.Lock()
        self.ctl = ctl.Babel(config.control_socket,
            weakref.proxy(self), self.network)

        self.onTimeout()

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
            for prefix, email, cert in q("SELECT * FROM cert"
                                         " WHERE cert IS NOT NULL"):
                try:
                    cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert)
                except crypto.Error:
                    continue
                x = utils.notAfter(cert)
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
        if method in ('versions', 'topology'):
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
            key = hashlib.sha1(struct.pack('Q',
                random.getrandbits(64))).digest()
            self.sessions.setdefault(client_prefix, [])[1:] = key,
        key = utils.encrypt(cert, key)
        sign = crypto.sign(self.key, key, 'sha1')
        assert len(key) == len(sign)
        return key + sign

    def getCert(self, client_prefix):
        assert self.lock.locked()
        return self.db.execute("SELECT cert FROM cert"
                               " WHERE prefix=? AND cert IS NOT NULL",
                               (client_prefix,)).next()[0]

    @rpc
    def requestToken(self, email):
        with self.lock:
            while True:
                # Generating token
                token = ''.join(random.sample(string.ascii_lowercase, 8))
                args = token, email, self.config.prefix_length, int(time.time())
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
                        return
                    email = None
                prefix = self.newPrefix(prefix_len)
                self.db.execute("UPDATE cert SET email = ? WHERE prefix = ?",
                                (email, prefix))
                if self.prefix is None:
                    self.prefix = prefix
                    self.db.execute(
                        "INSERT INTO config VALUES ('prefix',?)", (prefix,))
                return self.createCertificate(prefix, req.get_subject(),
                                                       req.get_pubkey())

    def createCertificate(self, client_prefix, subject, pubkey):
        cert = crypto.X509()
        cert.set_serial_number(0) # required for libssl < 1.0
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(self.cert_duration)
        cert.set_issuer(self.ca.get_subject())
        subject.CN = "%u/%u" % (int(client_prefix, 2), len(client_prefix))
        cert.set_subject(subject)
        cert.set_pubkey(pubkey)
        cert.sign(self.key, 'sha1')
        cert = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)
        self.db.execute("UPDATE cert SET cert = ? WHERE prefix = ?",
                        (cert, client_prefix))
        self.timeout = 1
        return cert

    @rpc
    def renewCertificate(self, cn):
        with self.lock:
            with self.db:
                pem = self.getCert(cn)
                cert = crypto.load_certificate(crypto.FILETYPE_PEM, pem)
                if utils.notAfter(cert) - RENEW_PERIOD < time.time():
                    pem = self.createCertificate(cn, cert.get_subject(),
                                                     cert.get_pubkey())
                return pem

    @rpc
    def getCa(self):
        return crypto.dump_certificate(crypto.FILETYPE_PEM, self.ca)

    @rpc
    def getPrefix(self, cn):
        return self.prefix

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
            address = utils.ipFromBin(self.network + peer), tunnel.PORT
            self.sock.sendto('\2', address)
            s = self.sock,
            timeout = 3
            end = timeout + time.time()
            # Loop because there may be answers from previous requests.
            while select.select(s, (), (), timeout)[0]:
                msg = self.sock.recv(1<<16)
                if msg[0] == '\1':
                    try:
                        msg = msg[1:msg.index('\n')]
                    except ValueError:
                        continue
                    if msg.split()[0] == peer:
                        break
                timeout = max(0, end - time.time())
            else:
                logging.info("Timeout while querying [%s]:%u", *address)
                return
            cert = self.getCert(cn)
        logging.info("Sending bootstrap peer: %s", msg)
        return utils.encrypt(cert, msg)

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
                    ver, address = self.sock.recvfrom(1<<16)
                    address = utils.binFromIp(address[0])
                    if (address.startswith(self.network) and
                        len(ver) > 1 and ver[0] in '\3\4' # BBB
                        ):
                        try:
                            peer_dict[max(filter(address[len(self.network):]
                                                 .startswith, peer_dict),
                                          key=len)] = ver[1:]
                        except ValueError:
                            pass
                if w:
                    x = peers.pop()
                    peer_dict[x] = None
                    x = utils.ipFromBin(self.network + x)
                    try:
                        self.sock.sendto('\3', (x, tunnel.PORT))
                    except socket.error:
                        pass
                elif not r:
                    break
        return repr(peer_dict)

    @rpc
    def topology(self):
        with self.lock:
            peers = deque(('%u/%u' % (int(self.prefix, 2), len(self.prefix)),))
            cookie = hex(random.randint(0, 1<<32))[2:]
            graph = dict.fromkeys(peers)
            s = self.sock,
            while True:
                r, w, _ = select.select(s, s if peers else (), (), 3)
                if r:
                    answer = self.sock.recv(1<<16)
                    if answer[0] == '\xfe':
                        answer = answer[1:].split('\n')[:-1]
                        if len(answer) >= 3 and answer[0] == cookie:
                            x = answer[3:]
                            assert answer[1] not in x, (answer, graph)
                            graph[answer[1]] = x[:int(answer[2])]
                            x = set(x).difference(graph)
                            peers += x
                            graph.update(dict.fromkeys(x))
                if w:
                    x = utils.binFromSubnet(peers.popleft())
                    x = utils.ipFromBin(self.network + x)
                    try:
                        self.sock.sendto('\xff%s\n' % cookie, (x, tunnel.PORT))
                    except socket.error:
                        pass
                elif not r:
                    break
            return repr(graph)


class RegistryClient(object):

    _hmac = None
    user_agent = "re6stnet/" + version.version

    def __init__(self, url, key_path=None, ca=None, auto_close=True):
        self.key_path = key_path
        self.ca = ca
        self.auto_close = auto_close
        scheme, host = splittype(url)
        host, path = splithost(host)
        host, port = splitport(host)
        self._conn = dict(http=httplib.HTTPConnection,
                          https=httplib.HTTPSConnection,
                          )[scheme](host, port, timeout=60)
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
                            crypto.verify(self.ca, h[n:], h[:n], 'sha1')
                            key = utils.decrypt(self.key_path, h[:n])
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
                    if response.status in (httplib.OK, httplib.NO_CONTENT) and (
                          not client_prefix or
                          hmac.HMAC(key, body, hashlib.sha1).digest() ==
                          base64.b64decode(response.msg[HMAC_HEADER])):
                        if self.auto_close and name != 'hello':
                            self._conn.close()
                        return body
                    if client_prefix:
                        self._hmac = None
            except Exception:
                logging.info(url, exc_info=1)
            else:
                logging.info('%s\nUnexpected response %s %s',
                             url, response.status, response.reason)
            self._conn.close()
        setattr(self, name, rpc)
        return rpc
