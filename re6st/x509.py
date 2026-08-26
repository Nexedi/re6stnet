# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, hmac, logging, os, struct, subprocess, time
from typing import Callable, Optional, Union

from cryptography import x509 as cx509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import Encoding


class LoadError(Exception):
    pass


try: # BBB: old cryptography
    from cryptography.hazmat.backends.openssl.backend import backend
    load_pem_private_key =  backend.load_pem_private_key
except AttributeError:
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from cryptography.x509 import \
        load_der_x509_certificate as _load_der_x509_certificate, \
        load_pem_x509_certificate as _load_pem_x509_certificate
else:
    _load_der_x509_certificate = backend.load_der_x509_certificate
    _load_pem_x509_certificate = backend.load_pem_x509_certificate

def load_pem_x509_certificate(data):
    try:
        return _load_pem_x509_certificate(data)
    except ValueError as e:
        raise LoadError(e) from e

def load_der_x509_certificate(data):
    try:
        return _load_der_x509_certificate(data)
    except ValueError as e:
        raise LoadError(e) from e

from . import utils
from .version import protocol

PADDING = padding.PKCS1v15()
PADDING_HASH = PADDING, hashes.SHA512()

_NAME_OID_MAP = {
    'C': cx509.oid.NameOID.COUNTRY_NAME,
    'ST': cx509.oid.NameOID.STATE_OR_PROVINCE_NAME,
    'L': cx509.oid.NameOID.LOCALITY_NAME,
    'O': cx509.oid.NameOID.ORGANIZATION_NAME,
    'OU': cx509.oid.NameOID.ORGANIZATIONAL_UNIT_NAME,
    'CN': cx509.oid.NameOID.COMMON_NAME,
    'emailAddress': cx509.oid.NameOID.EMAIL_ADDRESS,
    'serialNumber': cx509.oid.NameOID.SERIAL_NUMBER,
}
_OID_SHORT_MAP = {v: k for k, v in _NAME_OID_MAP.items()}

def create_csr_pem(pkey_pem: bytes, subject_attrs: dict) -> bytes:
    if isinstance(pkey_pem, str):
        pkey_pem = pkey_pem.encode()
    key = load_pem_private_key(pkey_pem, password=None)
    name_attrs = []
    for k, v in subject_attrs.items():
        oid = _NAME_OID_MAP.get(k)
        if oid is None:
            raise ValueError("Unknown subject attribute: %s" % k)
        name_attrs.append(cx509.NameAttribute(oid, v))
    csr = cx509.CertificateSigningRequestBuilder().subject_name(
        cx509.Name(name_attrs)
    ).sign(key, hashes.SHA512())
    return csr.public_bytes(Encoding.PEM)

def parse_csr(csr_pem):
    if isinstance(csr_pem, str):
        csr_pem = csr_pem.encode()
    csr = cx509.load_pem_x509_csr(csr_pem)
    return csr.subject, csr.public_key()

def newHmacSecret() -> bytes:
    return utils.newHmacSecret(int(time.time() * 1000000))

def _cert_subject_cn(cert) -> str:
    for attr in cert.subject:
        if attr.oid == cx509.oid.NameOID.COMMON_NAME:
            return attr.value
    raise ValueError("No CN in certificate subject")

def networkFromCa(ca) -> str:
    return bin(ca.serial_number)[3:]

def subnetFromCert(cert) -> str:
    return _cert_subject_cn(cert)

def notBefore(cert) -> int:
    return int(cert.not_valid_before_utc.timestamp())

def notAfter(cert) -> int:
    return int(cert.not_valid_after_utc.timestamp())

def encrypt(cert, data):
    return cert.public_key().encrypt(data, PADDING)

def fingerprint(cert: cx509.Certificate, alg='sha1'):
    return hashlib.new(alg, cert.public_bytes(Encoding.DER))

def maybe_renew(path: str, cert, info: str,
                renew: Callable[[], bytes],
                force=False) -> tuple:
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
            if not pem or pem == cert.public_bytes(Encoding.PEM):
                exc_info = 0
                break
            cert = load_pem_x509_certificate(pem)
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

    def __init__(self, ca: str, key: str, cert: Optional[str]=None):
        self.ca_path = ca
        self.cert_path = cert
        self.key_path = key
        with open(ca, "rb") as f:
            self.ca = load_pem_x509_certificate(f.read())
        with open(key, "rb") as f:
            self.key = load_pem_private_key(f.read(), password=None)
        if cert:
            with open(cert, "rb") as f:
                self.cert = self.loadVerify(f.read())

    @property
    def prefix(self) -> str:
        return utils.binFromSubnet(subnetFromCert(self.cert))

    @property
    def network(self) -> str:
        return networkFromCa(self.ca)

    @property
    def subject_serial(self) -> int:
        attrs = self.cert.subject.get_attributes_for_oid(
            cx509.oid.NameOID.SERIAL_NUMBER)
        return int(attrs[0].value) if attrs else 0

    @property
    def openvpn_args(self) -> tuple[str, ...]:
        return ('--ca', self.ca_path,
                '--cert', self.cert_path,
                '--key', self.key_path)

    def maybeRenew(self, registry, crl) -> int:
        self.cert, next_renew = maybe_renew(self.cert_path, self.cert,
              "Certificate", lambda: registry.renewCertificate(self.prefix),
              self.cert.serial_number in crl)
        self.ca, ca_renew = maybe_renew(self.ca_path, self.ca,
              "CA Certificate", registry.getCa)
        return min(next_renew, ca_renew)

    def loadVerify(self, cert, strict=False):
        if cert[:5] == b'-----':
            cert_pem = cert
            try:
                r = load_pem_x509_certificate(cert)
            except Exception as e:
                raise VerifyError(None, None,
                    'unable to load certificate') from e
        else:
            try:
                r = load_der_x509_certificate(cert)
            except Exception as e:
                raise VerifyError(None, None,
                    'unable to load certificate') from e
            cert_pem = r.public_bytes(Encoding.PEM)
        args = ['openssl', 'verify', '-CAfile', self.ca_path]
        if not strict:
            args += '-attime', str(min(int(time.time()),
                max(notBefore(self.ca), notBefore(r))))
        p = utils.Popen(args, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        out, err = p.communicate(cert_pem)
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

    def verify(self, *args):
        self.ca.public_key().verify(*args, *PADDING_HASH)

    def sign(self, data: bytes) -> bytes:
        return self.key.sign(data, *PADDING_HASH)

    def decrypt(self, data: bytes) -> bytes:
        return self.key.decrypt(data, PADDING)

    def verifyVersion(self, version):
        try:
            n = 1 + (version[0] >> 5) # see utils.unpackInteger
            self.verify(version[n:], version[:n])
        except (IndexError, InvalidSignature) as e:
            raise VerifyError('invalid network version') from e


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
    cert: cx509.Certificate

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

    def hello0(self, cert) -> bytes:
        if self._hello < time.time():
            try:
                # Always assume peer is not old, in case it has just upgraded,
                # else we would be stuck with the old protocol.
                msg = (b'\0\0\0\1'
                    + PACKED_PROTOCOL
                    + fingerprint(self.cert).digest())
            except AttributeError:
                msg = b'\0\0\0\0'
            return msg + cert.public_bytes(Encoding.DER)

    def hello0Sent(self):
        self._hello = time.time() + 60

    def hello(self, cert: Cert, protocol: int) -> bytes:
        key = self._key = newHmacSecret()
        h = encrypt(self.cert, key)
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

    def verify(self, *args):
        self.cert.public_key().verify(*args, *PADDING_HASH)

    seqno_struct = struct.Struct("!L")

    def decode(self, msg: bytes, _unpack=seqno_struct.unpack) \
            -> Union[tuple[int, bytes, Optional[int]], bytes]:
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
