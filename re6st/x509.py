# -*- coding: utf-8 -*-
import calendar, hashlib, hmac, logging, os, struct, subprocess, threading, time
from datetime import datetime
from OpenSSL import crypto
from . import utils

def newHmacSecret():
    x = datetime.utcnow()
    return utils.newHmacSecret(int(time.mktime(x.timetuple())) * 1000000
                                + x.microsecond)

def networkFromCa(ca):
    return bin(ca.get_serial_number())[3:]

def subnetFromCert(cert):
    return cert.get_subject().CN

def notAfter(cert):
    return calendar.timegm(time.strptime(cert.get_notAfter(),'%Y%m%d%H%M%SZ'))

def openssl(*args):
    return utils.Popen(('openssl',) + args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

def encrypt(cert, data):
    r, w = os.pipe()
    try:
        threading.Thread(target=os.write, args=(w, cert)).start()
        p = openssl('rsautl', '-encrypt', '-certin',
                    '-inkey', '/proc/self/fd/%u' % r)
        out, err = p.communicate(data)
    finally:
        os.close(r)
        os.close(w)
    if p.returncode:
        raise subprocess.CalledProcessError(p.returncode, 'openssl', err)
    return out

def fingerprint(cert, alg='sha1'):
    return hashlib.new(alg, crypto.dump_certificate(crypto.FILETYPE_ASN1, cert))

def maybe_renew(path, cert, info, renew, force=False):
    from .registry import RENEW_PERIOD
    while True:
        if force:
            force = False
        else:
            next_renew = notAfter(cert) - RENEW_PERIOD
            if time.time() < next_renew:
                return cert, next_renew
        try:
            pem = renew()
            if not pem or pem == crypto.dump_certificate(
                  crypto.FILETYPE_PEM, cert):
                exc_info = 0
                break
            cert = crypto.load_certificate(crypto.FILETYPE_PEM, pem)
        except Exception:
            exc_info = 1
            break
        new_path = path + '.new'
        with open(new_path, 'w') as f:
            f.write(pem)
        try:
            s = os.stat(path)
            os.chown(new_path, s.st_uid, s.st_gid)
        except OSError:
            pass
        os.rename(new_path, path)
        logging.info("%s renewed until %s UTC",
            info, time.asctime(time.gmtime(notAfter(cert))))
    logging.error("%s not renewed. Will retry tomorrow.",
                  info, exc_info=exc_info)
    return cert, time.time() + 86400


class VerifyError(Exception):
    pass

class NewSessionError(Exception):
    pass


class Cert(object):

    def __init__(self, ca, key, cert=None):
        self.ca_path = ca
        self.cert_path = cert
        self.key_path = key
        with open(ca) as f:
            self.ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        with open(key) as f:
            self.key = crypto.load_privatekey(crypto.FILETYPE_PEM, f.read())
        if cert:
            with open(cert) as f:
                self.cert = self.loadVerify(f.read())

    @property
    def prefix(self):
        return utils.binFromSubnet(subnetFromCert(self.cert))

    @property
    def network(self):
        return networkFromCa(self.ca)

    @property
    def subject_serial(self):
        return int(self.cert.get_subject().serialNumber)

    @property
    def openvpn_args(self):
        return ('--ca', self.ca_path,
                '--cert', self.cert_path,
                '--key', self.key_path)

    def maybeRenew(self, registry, crl):
        self.cert, next_renew = maybe_renew(self.cert_path, self.cert,
              "Certificate", lambda: registry.renewCertificate(self.prefix),
              self.cert.get_serial_number() in crl)
        self.ca, ca_renew = maybe_renew(self.ca_path, self.ca,
              "CA Certificate", registry.getCa)
        return min(next_renew, ca_renew)

    def loadVerify(self, cert, strict=False, type=crypto.FILETYPE_PEM):
        try:
            r = crypto.load_certificate(type, cert)
        except crypto.Error:
            raise VerifyError(None, None, 'unable to load certificate')
        if type != crypto.FILETYPE_PEM:
            cert = crypto.dump_certificate(crypto.FILETYPE_PEM, r)
        p = openssl('verify', '-CAfile', self.ca_path)
        out, err = p.communicate(cert)
        if p.returncode or strict:
            for x in out.splitlines():
                if x.startswith('error '):
                    x, msg = x.split(':', 1)
                    _, code, _, depth, _ = x.split(None, 4)
                    raise VerifyError(int(code), int(depth), msg)
        return r

    def verify(self, sign, data):
        crypto.verify(self.ca, sign, data, 'sha512')

    def sign(self, data):
        return crypto.sign(self.key, data, 'sha512')

    def decrypt(self, data):
        p = openssl('rsautl', '-decrypt', '-inkey', self.key_path)
        out, err = p.communicate(data)
        if p.returncode:
            raise subprocess.CalledProcessError(p.returncode, 'openssl', err)
        return out

    def verifyVersion(self, version):
        try:
            n = 1 + (ord(version[0]) >> 5)
            self.verify(version[n:], version[:n])
        except (IndexError, crypto.Error):
            raise VerifyError(None, None, 'invalid network version')


class Peer(object):
    """
    UDP:    A ─────────────────────────────────────────────> B

    hello0:    0, A
               1, fingerprint(B), A
    hello:     2, X = encrypt(B, secret), sign(A, X)
    !hello:    #, type, value, hmac(secret, payload)
               └── payload ──┘

    new secret > old secret
    (timestamp + random bits)

    Reject messages with # smaller or equal than previously processed.

    Yes, we do UDP on purpose. The only drawbacks are:
    - The limited size of packets, but they are big enough for a network
      using 4096-bits RSA keys.
    - hello0 packets (0 & 1) are subject to DoS, because verifying a
      certificate uses much CPU. A solution would be to use TCP until the
      secret is exchanged and continue with UDP.

    The fingerprint is only used to quickly know if peer's certificate has
    changed. It must be short enough to not exceed packet size when using
    certificates with 4096-bit keys. A weak algorithm is ok as long as there
    is no accidental collision. So SHA-1 looks fine.
    """
    _hello = _last = 0
    _key = newHmacSecret()
    serial = None
    stop_date = float('inf')
    version = ''

    def __init__(self, prefix):
        self.prefix = prefix

    @property
    def connected(self):
        return self._last is None or time.time() < self._last + 60

    subject_serial = Cert.subject_serial

    def __ne__(self, other):
        raise AssertionError
    __eq__ = __ge__ = __le__ = __ne__

    def __gt__(self, other):
        return self.prefix > (other if type(other) is str else other.prefix)
    def __lt__(self, other):
        return self.prefix < (other if type(other) is str else other.prefix)

    def hello0(self, cert):
        if self._hello < time.time():
            try:
                msg = '\0\0\0\1' + fingerprint(self.cert).digest()
            except AttributeError:
                msg = '\0\0\0\0'
            return msg + crypto.dump_certificate(crypto.FILETYPE_ASN1, cert)

    def hello0Sent(self):
        self._hello = time.time() + 60

    def hello(self, cert):
        key = self._key = newHmacSecret()
        h = encrypt(crypto.dump_certificate(crypto.FILETYPE_PEM, self.cert),
                    key)
        self._i = self._j = 2
        self._last = 0
        return '\0\0\0\2' + h + cert.sign(h)

    def _hmac(self, msg):
        return hmac.HMAC(self._key, msg, hashlib.sha1).digest()

    def newSession(self, key):
        if key <= self._key:
            raise NewSessionError(self._key, key)
        self._key = key
        self._i = self._j = 2
        self._last = None

    def verify(self, sign, data):
        crypto.verify(self.cert, sign, data, 'sha512')

    seqno_struct = struct.Struct("!L")

    def decode(self, msg, _unpack=seqno_struct.unpack):
        seqno, = _unpack(msg[:4])
        if seqno <= 2:
            return seqno, msg[4:]
        i = -utils.HMAC_LEN
        if self._hmac(msg[:i]) == msg[i:] and self._i < seqno:
            self._last = None
            self._i = seqno
            return msg[4:i]

    def encode(self, msg, _pack=seqno_struct.pack):
        self._j += 1
        msg = _pack(self._j) + msg
        return msg + self._hmac(msg)

    del seqno_struct

    def sent(self):
        if not self._last:
            self._last = time.time()
