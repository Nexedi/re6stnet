import argparse, time, struct, socket
from OpenSSL import crypto

verbose = 0

def log(message, verbose_level):
    if verbose >= verbose_level:
        print time.strftime("%d-%m-%Y %H:%M:%S : " + message)

def binFromIp(ip):
    ip1, ip2 = struct.unpack('>QQ', socket.inet_pton(socket.AF_INET6, ip))
    return bin(ip1)[2:].rjust(64, '0') + bin(ip2)[2:].rjust(64, '0')

def ipFromBin(prefix):
    prefix = hex(int(prefix, 2))[2:]
    ip = ''
    for i in xrange(0, len(prefix) - 1, 4):
        ip += prefix[i:i+4] + ':'
    return ip.rstrip(':')

def ipFromPrefix(vifibnet, prefix, prefix_len):
    prefix = bin(int(prefix))[2:].rjust(prefix_len, '0')
    ip_t = (vifibnet + prefix).ljust(128, '0')
    return ipFromBin(ip_t), prefix

def networkFromCa(ca_path):
    # Get network prefix from ca.crt
    with open(ca_path, 'r') as f:
        ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        return bin(ca.get_serial_number())[3:]

def ipFromCert(network, cert_path):
    # Get ip from cert.crt
    with open(cert_path, 'r') as f:
        cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        subject = cert.get_subject()
        prefix, prefix_len = subject.CN.split('/')
        return ipFromPrefix(network, prefix, int(prefix_len))

def address_list(address_set):
    return ';'.join(map(','.join, address_set))

def address_set(address_list):
    return set(tuple(address.split(','))
        for address in address_list.split(';'))
