import time
from datetime import datetime, timedelta, timezone
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
    key = rsa.generate_private_key(65537, 2048, backend=x509.backend)
    req = cx509.CertificateSigningRequestBuilder().subject_name(
        cx509.Name([cx509.NameAttribute(NameOID.COMMON_NAME, "test ca")])
    ).sign(key, hashes.SHA256(), backend=x509.backend)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ), req.public_bytes(serialization.Encoding.PEM)

def generate_cert(ca, ca_key, csr, prefix, serial, not_after=None):
    """generate a certificate

    return
        certificate in pem format (bytes)
    """
    if type(ca) is bytes:
        ca = x509.load_pem_x509_certificate(ca)
    if type(ca_key) is bytes:
        ca_key = x509.load_pem_private_key(ca_key, password=None)
    csr_obj = x509.load_pem_x509_csr(csr)

    subject = csr_obj.subject
    if prefix:
        x = [x for x in subject if x.oid != NameOID.COMMON_NAME]
        x.append(cx509.NameAttribute(NameOID.COMMON_NAME, prefix2cn(prefix)))
        subject = cx509.Name(x)

    now = datetime.now(timezone.utc)
    if not_after:
        not_after = datetime.fromtimestamp(not_after, tz=timezone.utc)
    else:
        not_after = now + timedelta(
            seconds=registry.RegistryServer.cert_duration)

    cert = cx509.CertificateBuilder(
        issuer_name=ca.subject,
        subject_name=subject,
        public_key=csr_obj.public_key(),
        not_valid_before=now,
        not_valid_after=not_after,
        serial_number=serial,
    ).add_extension(
        cx509.BasicConstraints(ca=False, path_length=None), critical=True
    ).sign(ca_key, hashes.SHA512(), backend=x509.backend)
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
    key = rsa.generate_private_key(65537, 2048, backend=x509.backend)
    now = datetime.now(timezone.utc)
    subject = cx509.Name([
        cx509.NameAttribute(NameOID.COUNTRY_NAME, "FR"),
        cx509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Lille"),
        cx509.NameAttribute(NameOID.LOCALITY_NAME, "Lille"),
        cx509.NameAttribute(NameOID.ORGANIZATION_NAME, "nexedi"),
        cx509.NameAttribute(NameOID.COMMON_NAME, "TEST-CA"),
    ])
    cert = cx509.CertificateBuilder(
        issuer_name=subject,
        subject_name=subject,
        public_key=key.public_key(),
        not_valid_before=now,
        not_valid_after=now + timedelta(
            seconds=registry.RegistryServer.cert_duration),
        serial_number=serial,
    ).add_extension(
        cx509.BasicConstraints(ca=True, path_length=None), critical=True
    ).sign(key, hashes.SHA512(), backend=x509.backend)

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
