import argparse, time, struct, socket, logging
from OpenSSL import crypto

logging_levels = logging.WARNING, logging.INFO, logging.DEBUG, 5


def setupLog(log_level, **kw):
    if log_level:
        logging.basicConfig(level=logging_levels[log_level-1],
            format='%(asctime)s %(levelname)-9s %(message)s',
            datefmt='%d-%m-%Y %H:%M:%S', **kw)
    else:
        logging.disable(logging.CRITICAL)
    logging.addLevelName(5, 'TRACE')
    logging.trace = lambda *args, **kw: logging.log(5, *args, **kw)

class ArgParser(argparse.ArgumentParser):

    def convert_arg_line_to_args(self, arg_line):
        arg_line = arg_line.split('#')[0].rstrip()
        if arg_line:
            if arg_line.startswith('@'):
                yield arg_line
                return
            for arg in ('--' + arg_line.lstrip('--')).split():
                if arg.strip():
                    yield arg

def binFromIp(ip):
    ip1, ip2 = struct.unpack('>QQ', socket.inet_pton(socket.AF_INET6, ip))
    return bin(ip1)[2:].rjust(64, '0') + bin(ip2)[2:].rjust(64, '0')


def ipFromBin(prefix, suffix=''):
    ip = prefix + suffix.rjust(128 - len(prefix), '0')
    return socket.inet_ntop(socket.AF_INET6,
        struct.pack('>QQ', int(ip[:64], 2), int(ip[64:], 2)))

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
        prefix = bin(int(prefix))[2:].rjust(int(prefix_len), '0')
        return ipFromBin(network + prefix, '1'), prefix

def address_str(address):
    return ';'.join(map(','.join, address))


def address_list(address_list):
    return list(tuple(address.split(','))
        for address in address_list.split(';'))


def binFromSubnet(subnet):
    p, l = subnet.split('/')
    return bin(int(p))[2:].rjust(int(l), '0')
