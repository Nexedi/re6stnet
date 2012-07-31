import argparse, time, struct, socket, logging
from OpenSSL import crypto

logging_levels = logging.WARNING, logging.INFO, logging.DEBUG, 5


def setupLog(log_level):
    logging.basicConfig(level=logging_levels[log_level],
            format='%(asctime)s : %(message)s',
            datefmt='%d-%m-%Y %H:%M:%S')
    logging.addLevelName(5, 'TRACE')
    logging.trace = lambda *args, **kw: logging.log(5, *args, **kw)


def binFromIp(ip):
    ip1, ip2 = struct.unpack('>QQ', socket.inet_pton(socket.AF_INET6, ip))
    return bin(ip1)[2:].rjust(64, '0') + bin(ip2)[2:].rjust(64, '0')


def ipFromBin(prefix):
    prefix = hex(int(prefix, 2))[2:]
    ip = ''
    for i in xrange(0, len(prefix) - 1, 4):
        ip += prefix[i:i + 4] + ':'
    return ip.rstrip(':')


def ipFromPrefix(re6stnet, prefix, prefix_len):
    prefix = bin(int(prefix))[2:].rjust(prefix_len, '0')
    ip_t = (re6stnet + prefix).ljust(127, '0').ljust(128, '1')
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


def address_str(address_set):
    return ';'.join(map(','.join, address_set))


def address_list(address_list):
    return list(tuple(address.split(','))
        for address in address_list.split(';'))
