import time
from cryptography import x509 as cx509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone

from re6st import registry, x509
from re6st.x509 import load_pem_x509_certificate, load_pem_private_key


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
        certificate in pem format (bytes)
    """
    if type(ca) is bytes:
        ca = load_pem_x509_certificate(ca)
    if type(ca_key) is bytes:
        ca_key = load_pem_private_key(ca_key, password=None)
    csr_obj = cx509.load_pem_x509_csr(csr)

    if prefix:
        cn = prefix2cn(prefix)
    else:
        cn = None
    name_attrs = []
    for attr in csr_obj.subject:
        if cn and attr.oid == NameOID.COMMON_NAME:
            name_attrs.append(cx509.NameAttribute(attr.oid, cn))
        else:
            name_attrs.append(cx509.NameAttribute(attr.oid, attr.value))
    if cn and not any(a.oid == NameOID.COMMON_NAME for a in csr_obj.subject):
        name_attrs.append(cx509.NameAttribute(NameOID.COMMON_NAME, cn))
    subject = cx509.Name(name_attrs)

    if not_after:
        na_dt = datetime.fromtimestamp(not_after, tz=timezone.utc)
        nb_dt = na_dt - timedelta(seconds=1)
    else:
        nb_dt = datetime.now(timezone.utc)
        na_dt = nb_dt + timedelta(seconds=registry.RegistryServer.cert_duration)

    builder = cx509.CertificateBuilder()
    builder = builder.issuer_name(ca.subject)
    builder = builder.subject_name(subject)
    builder = builder.public_key(csr_obj.public_key())
    builder = builder.not_valid_before(nb_dt)
    builder = builder.not_valid_after(na_dt)
    builder = builder.serial_number(serial)
    builder = builder.add_extension(
        cx509.BasicConstraints(ca=False, path_length=None), critical=True)
    cert = builder.sign(ca_key, hashes.SHA512())
    return cert.public_bytes(serialization.Encoding.PEM)

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
    return key, cert (cryptography objects) """
    key = rsa.generate_private_key(65537, 2048)
    now = datetime.now(timezone.utc)
    subject = cx509.Name([
        cx509.NameAttribute(NameOID.COUNTRY_NAME, "FR"),
        cx509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Lille"),
        cx509.NameAttribute(NameOID.LOCALITY_NAME, "Lille"),
        cx509.NameAttribute(NameOID.ORGANIZATION_NAME, "nexedi"),
        cx509.NameAttribute(NameOID.COMMON_NAME, "TEST-CA"),
    ])
    cert = cx509.CertificateBuilder()
    cert = cert.issuer_name(subject)
    cert = cert.subject_name(subject)
    cert = cert.public_key(key.public_key())
    cert = cert.not_valid_before(now)
    cert = cert.not_valid_after(now + timedelta(
        seconds=registry.RegistryServer.cert_duration))
    cert = cert.serial_number(serial)
    cert = cert.add_extension(
        cx509.BasicConstraints(ca=True, path_length=None), critical=True)
    cert = cert.sign(key, hashes.SHA512())

    with open(pkey_file, 'wb') as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
    with open(cert_file, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return key, cert


def prefix2cn(prefix: str) -> str:
    return "%u/%u" % (int(prefix, 2), len(prefix))

def serial2prefix(serial: int) -> str:
    return bin(serial)[2:].rjust(16, '0')

def decrypt(pkey: bytes, incontent: bytes) -> bytes:
    pkey = x509.load_pem_private_key(pkey, password=None)
    return pkey.decrypt(incontent, x509.PADDING)
