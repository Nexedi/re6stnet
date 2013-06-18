import base64, hmac, hashlib, httplib, inspect, logging, mailbox, os, random
import select, smtplib, socket, sqlite3, string, struct, threading, time
from collections import deque
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from email.mime.text import MIMEText
from OpenSSL import crypto
from urllib import splittype, splithost, splitport, urlencode
from . import tunnel, utils

HMAC_HEADER = "Re6stHMAC"
RENEW_PERIOD = 30 * 86400


class getcallargs(type):

    def __init__(cls, name, bases, d):
        type.__init__(cls, name, bases, d)
        for n, f in d.iteritems():
            if n[0] == '_':
                continue
            try:
                args, varargs, varkw, defaults = inspect.getargspec(f)
            except TypeError:
                continue
            if varargs or varkw or defaults:
                continue
            f.getcallargs = eval("lambda %s: locals()" % ','.join(args[1:]))


class RegistryServer(object):

    __metaclass__ = getcallargs

    def __init__(self, config):
        self.config = config
        self.cert_duration = 365 * 86400
        self.lock = threading.Lock()
        self.sessions = {}

        if self.config.private:
            self.sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        else:
            logging.warning('You have declared no private address'
                    ', either this is the first start, or you should'
                    'check you configuration')

        # Database initializing
        utils.makedirs(os.path.dirname(self.config.db))
        self.db = sqlite3.connect(self.config.db, isolation_level=None,
                                                  check_same_thread=False)
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
        self._email = self.ca.get_subject().emailAddress

    def _handle_request(self, request, method, kw):
        m = getattr(self, method)
        if method in ('topology',) and \
           request.client_address[0] not in ('127.0.0.1', '::'):
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

    def hello(self, client_prefix):
        with self.lock:
            cert = self._getCert(client_prefix)
            key = hashlib.sha1(struct.pack('Q',
                random.getrandbits(64))).digest()
            self.sessions.setdefault(client_prefix, [])[1:] = key,
        key = utils.encrypt(cert, key)
        sign = crypto.sign(self.key, key, 'sha1')
        assert len(key) == len(sign)
        return key + sign

    def _getCert(self, client_prefix):
        assert self.lock.locked()
        return self.db.execute("SELECT cert FROM cert WHERE prefix = ?",
                               (client_prefix,)).next()[0]

    def requestToken(self, email):
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

        # Creating and sending email
        msg = MIMEText('Hello, your token to join re6st network is: %s\n'
                       % token)
        msg['Subject'] = '[re6stnet] Token Request'
        if self._email:
            msg['From'] = self._email
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
            s.sendmail(self._email, email, msg.as_string())
            s.quit()

    def _getPrefix(self, prefix_len):
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
        return self._getPrefix(prefix_len)

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
                prefix = self._getPrefix(prefix_len)
                self.db.execute("UPDATE cert SET email = ? WHERE prefix = ?",
                                (email, prefix))
                return self._createCertificate(prefix, req.get_subject(),
                                                       req.get_pubkey())

    def _createCertificate(self, client_prefix, subject, pubkey):
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
        return cert

    def renewCertificate(self, cn):
        with self.lock:
            with self.db:
                pem = self._getCert(cn)
                cert = crypto.load_certificate(crypto.FILETYPE_PEM, pem)
                if utils.notAfter(cert) - RENEW_PERIOD < time.time():
                    pem = self._createCertificate(cn, cert.get_subject(),
                                                      cert.get_pubkey())
                return pem

    def getCa(self):
        return crypto.dump_certificate(crypto.FILETYPE_PEM, self.ca)

    def getPrivateAddress(self, cn):
        return self.config.private

    def getBootstrapPeer(self, cn):
        with self.lock:
            cert = self._getCert(cn)
            address = self.config.private, tunnel.PORT
            self.sock.sendto('\2', address)
            peer = None
            while select.select([self.sock], [], [], peer is None)[0]:
                msg = self.sock.recv(1<<16)
                if msg[0] == '\1':
                    try:
                        peer = msg[1:].split('\n')[-2]
                    except IndexError:
                        peer = ''
        if peer is None:
            raise EnvironmentError("Timeout while querying [%s]:%u" % address)
        if not peer or peer.split()[0] == cn:
            raise LookupError("No bootstrap peer found")
        logging.info("Sending bootstrap peer: %s", peer)
        return utils.encrypt(cert, peer)

    def topology(self):
        with self.lock:
            is_registry = utils.binFromIp(self.config.private
                )[len(self.network):].startswith
            peers = deque('%u/%u' % (int(x, 2), len(x))
                for x, in self.db.execute("SELECT prefix FROM cert")
                if is_registry(x))
            assert len(peers) == 1
            cookie = hex(random.randint(0, 1<<32))[2:]
            graph = dict.fromkeys(peers)
            asked = 0
            while True:
                r, w, _ = select.select([self.sock],
                    [self.sock] if peers else [], [], 1)
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

    def __init__(self, url, key_path=None, ca=None, auto_close=True):
        self.key_path = key_path
        self.ca = ca
        self.auto_close = auto_close
        scheme, host = splittype(url)
        host, path = splithost(host)
        host, port = splitport(host)
        self._conn = dict(http=httplib.HTTPConnection,
                          https=httplib.HTTPSConnection,
                          )[scheme](host, port)
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
