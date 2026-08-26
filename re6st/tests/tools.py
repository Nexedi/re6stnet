import time
from OpenSSL import crypto
from cryptography import x509 as cx509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from re6st import registry, x509


def generate_csr():
    """generate a certificate request

    return:
        pkey and csr both in pem format
    """
    key = rsa.generate_private_key(65537, 2048)
    req = cx509.CertificateSigningRequestBuilder().subject_name(
        cx509.Name([cx509.NameAttribute(NameOID.COMMON_NAME, "test ca")])
    ).sign(key, hashes.SHA256())
    csr = req.public_bytes(serialization.Encoding.PEM)
    pkey = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return pkey, csr


def generate_cert(ca, ca_key, csr, prefix, serial, not_after=None):
    """generate a certificate

    return
        crypto.X509Cert in pem format
    """
    if type(ca) is bytes:
        ca = crypto.load_certificate(crypto.FILETYPE_PEM, ca)
    if type(ca_key) is bytes:
        ca_key = crypto.load_privatekey(crypto.FILETYPE_PEM, ca_key)
    csr_obj = cx509.load_pem_x509_csr(csr)

    cert = crypto.X509()
    cert.gmtime_adj_notBefore(0)
    if not_after:
        cert.set_notAfter(
            time.strftime("%Y%m%d%H%M%SZ", time.gmtime(not_after)).encode())
    else:
        cert.gmtime_adj_notAfter(registry.RegistryServer.cert_duration)
    subject = crypto.X509Name(crypto.X509().get_subject())
    for attr in csr_obj.subject:
        setattr(subject, attr.oid._name, attr.value)
    if prefix:
        subject.CN = prefix2cn(prefix)
    cert.set_subject(subject)
    cert.set_issuer(ca.get_subject())
    pubkey = crypto.load_publickey(
        crypto.FILETYPE_PEM,
        csr_obj.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
    )
    cert.set_pubkey(pubkey)
    cert.set_serial_number(serial)
    cert.sign(ca_key, 'sha512')
    return crypto.dump_certificate(crypto.FILETYPE_PEM, cert)

def create_cert_file(pkey_file, cert_file, ca, ca_key, prefix, serial):
    pkey, csr = generate_csr()
    cert = generate_cert(ca, ca_key, csr, prefix, serial)
    with open(pkey_file, 'wb') as f:
        f.write(pkey)
    with open(cert_file, 'wb') as f:
        f.write(cert)

    return pkey, cert



def create_ca_file(pkey_file, cert_file, serial=0x120010db80042):
    """create key and ca file with specify name
    return key, cert in pem format """
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)
    cert = crypto.X509()
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(registry.RegistryServer.cert_duration)
    subject= cert.get_subject()
    subject.C = "FR"
    subject.ST = "Lille"
    subject.L = "Lille"
    subject.O = "nexedi"
    subject.CN = "TEST-CA"
    cert.set_issuer(cert.get_subject())
    cert.set_serial_number(serial)
    cert.set_pubkey(key)
    cert.sign(key, "sha512")

    with open(pkey_file, 'wb') as pkey_file:
        pkey_file.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))
    with open(cert_file, 'wb') as cert_file:
        cert_file.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

    return key, cert


def prefix2cn(prefix: str) -> str:
    return "%u/%u" % (int(prefix, 2), len(prefix))

def serial2prefix(serial: int) -> str:
    return bin(serial)[2:].rjust(16, '0')

def decrypt(pkey: bytes, incontent: bytes) -> bytes:
    pkey = x509.load_pem_private_key(pkey, password=None)
    return pkey.decrypt(incontent, x509.PADDING)
