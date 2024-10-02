# -*- coding: utf-8 -*-
import calendar, hashlib, hmac, logging, os, struct, subprocess, threading, time
from typing import Callable, Any

from OpenSSL import crypto
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import load_pem_x509_certificate

from . import utils
from .version import protocol

def newHmacSecret() -> bytes:
    return utils.newHmacSecret(int(time.time() * 1000000))

def networkFromCa(ca: crypto.X509) -> str:
    # TODO: will be ca.serial_number after migration to cryptography
    return bin(ca.get_serial_number())[3:]

def subnetFromCert(cert: crypto.X509) -> str:
    return cert.get_subject().CN

def notBefore(cert: crypto.X509) -> int:
    return calendar.timegm(time.strptime(cert.get_notBefore().decode(),
                                         '%Y%m%d%H%M%SZ'))

def notAfter(cert: crypto.X509) -> int:
    return calendar.timegm(time.strptime(cert.get_notAfter().decode(),
                                         '%Y%m%d%H%M%SZ'))

def openssl(*args: str, fds=[]) -> utils.Popen:
    return utils.Popen(('openssl',) + args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, pass_fds=fds)

def encrypt(cert: bytes, data: bytes) -> bytes:
    r, w = os.pipe()
    try:
        threading.Thread(target=os.write, args=(w, cert)).start()
        p = openssl('rsautl', '-encrypt', '-certin',
                    '-inkey', '/proc/self/fd/%u' % r, fds=[r])
        out, err = p.communicate(data)
    finally:
        os.close(r)
        os.close(w)
    if p.returncode:
        raise subprocess.CalledProcessError(p.returncode, 'openssl', err)
    return out

def fingerprint(cert: crypto.X509, alg='sha1'):
    return hashlib.new(alg, crypto.dump_certificate(crypto.FILETYPE_ASN1, cert))

def maybe_renew(path: str, cert: crypto.X509, info: str,
                renew: Callable[[], bytes],
                force=False) -> tuple[crypto.X509, int]:
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
        with open(new_path, 'wb') as f:
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


class Cert:

    def __init__(self, ca: str, key: str, cert: str | None=None):
        self.ca_path = ca
        self.cert_path = cert
        self.key_path = key
        # TODO: finish migration from old OpenSSL module to cryptography
        with open(ca, "rb") as f:
            ca_pem = f.read()
            self.ca = crypto.load_certificate(crypto.FILETYPE_PEM, ca_pem)
            self.ca_crypto = load_pem_x509_certificate(ca_pem)
        with open(key, "rb") as f:
            key_pem = f.read()
            self.key = crypto.load_privatekey(crypto.FILETYPE_PEM, key_pem)
            self.key_crypto = load_pem_private_key(key_pem, password=None)
        if cert:
            with open(cert) as f:
                self.cert = self.loadVerify(f.read().encode())

    @property
    def prefix(self) -> str:
        return utils.binFromSubnet(subnetFromCert(self.cert))

    @property
    def network(self) -> str:
        return networkFromCa(self.ca)

    @property
    def subject_serial(self) -> int:
        return int(self.cert.get_subject().serialNumber)

    @property
    def openvpn_args(self) -> tuple[str, ...]:
        return ('--ca', self.ca_path,
                '--cert', self.cert_path,
                '--key', self.key_path)

    def maybeRenew(self, registry, crl) -> int:
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
        args = ['verify', '-CAfile', self.ca_path]
        if not strict:
            args += '-attime', str(min(int(time.time()),
                max(notBefore(self.ca), notBefore(r))))
        p = openssl(*args)
        out, err = p.communicate(cert)
        if 1: # BBB: Old OpenSSL could return 0 in case of errors.
          if err is None: # utils.Popen failed with ENOMEM
            raise VerifyError(None, None,
                "error running openssl, assuming cert is invalid")
          # BBB: With old versions of openssl, detailed
          #      error is printed to standard output.
          for stream in err, out:
            for x in stream.decode(errors='replace').splitlines():
                if x.startswith('error '):
                    x, msg = x.split(':', 1)
                    _, code, _, depth, _ = x.split(None, 4)
                    raise VerifyError(int(code), int(depth), msg.strip())
        return r

    def verify(self, sign: bytes, data: bytes):
        pub_key = self.ca_crypto.public_key()
        pub_key.verify(
            sign,
            data,
            padding.PKCS1v15(),
            hashes.SHA512()
        )

    def sign(self, data: bytes) -> bytes:
        return self.key_crypto.sign(
            data,
            padding.PKCS1v15(),
            hashes.SHA512()
        )

    def decrypt(self, data: bytes) -> bytes:
        p = openssl('rsautl', '-decrypt', '-inkey', self.key_path)
        out, err = p.communicate(data)
        if p.returncode:
            raise subprocess.CalledProcessError(p.returncode, 'openssl', err)
        return out

    def verifyVersion(self, version):
        try:
            n = 1 + (version[0] >> 5)
            self.verify(version[n:], version[:n])
        except (IndexError, crypto.Error):
            raise VerifyError(None, None, 'invalid network version')


PACKED_PROTOCOL = utils.packInteger(protocol)


class Peer:
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
    version = b''
    cert: crypto.X509

    def __init__(self, prefix: str):
        self.prefix = prefix

    @property
    def connected(self):
        return self._last is None or time.time() < self._last + 60

    def __ne__(self, other):
        raise AssertionError
    __eq__ = __ge__ = __le__ = __ne__

    def __gt__(self, other):
        return self.prefix > (other if type(other) is str else other.prefix)
    def __lt__(self, other):
        return self.prefix < (other if type(other) is str else other.prefix)

    def hello0(self, cert: crypto.X509) -> bytes:
        if self._hello < time.time():
            try:
                # Always assume peer is not old, in case it has just upgraded,
                # else we would be stuck with the old protocol.
                msg = (b'\0\0\0\1'
                    + PACKED_PROTOCOL
                    + fingerprint(self.cert).digest())
            except AttributeError:
                msg = b'\0\0\0\0'
            return msg + crypto.dump_certificate(crypto.FILETYPE_ASN1, cert)

    def hello0Sent(self):
        self._hello = time.time() + 60

    def hello(self, cert: Cert, protocol: int) -> bytes:
        key = self._key = newHmacSecret()
        h = encrypt(crypto.dump_certificate(crypto.FILETYPE_PEM, self.cert),
                    key)
        self._i = self._j = 2
        self._last = 0
        self.protocol = protocol
        return b''.join((b'\0\0\0\2', PACKED_PROTOCOL if protocol else b'',
                        h, cert.sign(h)))

    def _hmac(self, msg: bytes) -> bytes:
        return hmac.HMAC(self._key, msg, hashlib.sha1).digest()

    def newSession(self, key: bytes, protocol: int):
        if key <= self._key:
            raise NewSessionError(self._key, key)
        self._key = key
        self._i = self._j = 2
        self._last = None
        self.protocol = protocol

    def verify(self, sign: bytes, data: bytes):
        crypto.verify(self.cert, sign, data, 'sha512')

    seqno_struct = struct.Struct("!L")

    def decode(self, msg: bytes, _unpack=seqno_struct.unpack) \
            -> tuple[int, bytes, int | None] | bytes:
        seqno, = _unpack(msg[:4])
        if seqno <= 2:
            msg = msg[4:]
            if seqno:
                protocol, n = utils.unpackInteger(msg) or (0, 0)
                msg = msg[n:]
            else:
                protocol = None
            return seqno, msg, protocol
        i = -utils.HMAC_LEN
        if self._hmac(msg[:i]) == msg[i:] and self._i < seqno:
            self._last = None
            self._i = seqno
            return msg[4:i]

    def encode(self, msg: str | bytes, _pack=seqno_struct.pack) -> bytes:
        self._j += 1
        if type(msg) is str:
            msg = msg.encode()
        msg = _pack(self._j) + msg
        return msg + self._hmac(msg)

    del seqno_struct

    def sent(self):
        if not self._last:
            self._last = time.time()
