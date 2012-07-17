import time
import argparse
from OpenSSL import crypto

def log(message, verbose_level):
    if config.verbose >= verbose_level:
        print time.strftime("%d-%m-%Y %H:%M:%S : " + message)

def ipFromBin(prefix):
    prefix = hex(int(prefix, 2))[2:]
    ip = ''
    for i in xrange(0, len(prefix) - 1, 4):
        ip += prefix[i:i+4] + ':'
    return ip.rstrip(':')

def ipFromPrefix(vifibnet, prefix, prefix_len):
    prefix = bin(int(prefix))[2:].rjust(prefix_len, '0')
    ip_t = (vifibnet + prefix).ljust(128, '0')
    return ipFromBin(ip_t)

def getConfig():
    global config
    parser = argparse.ArgumentParser(
            description='Resilient virtual private network application')
    _ = parser.add_argument
    # Server address MUST be a vifib address ( else requests will be denied )
    _('--server', required=True,
            help='Address for peer discovery server')
    _('--server-port', required=True, type=int,
            help='Peer discovery server port')
    _('-l', '--log', default='/var/log',
            help='Path to vifibnet logs directory')
    _('--client-count', default=2, type=int,
            help='Number of client connections')
    # TODO: use maxpeer
    _('--max-clients', default=10, type=int,
            help='the number of peers that can connect to the server')
    _('--refresh-time', default=300, type=int,
            help='the time (seconds) to wait before changing the connections')
    _('--refresh-count', default=1, type=int,
            help='The number of connections to drop when refreshing the connections')
    _('--db', default='/var/lib/vifibnet/peers.db',
            help='Path to peers database')
    _('--dh', required=True,
            help='Path to dh file')
    _('--babel-state', default='/var/lib/vifibnet/babel_state',
            help='Path to babeld state-file')
    _('--verbose', '-v', default=0, type=int,
            help='Defines the verbose level')
    _('--ca', required=True,
            help='Path to the certificate authority file')
    _('--cert', required=True,
            help='Path to the certificate file')
    _('--ip', required=True, dest='external_ip',
            help='Ip address of the machine on the internet')
    # Openvpn options
    _('openvpn_args', nargs=argparse.REMAINDER,
            help="Common OpenVPN options (e.g. certificates)")
    config = parser.parse_args()

    # Get network prefix from ca.crt
    with open(config.ca, 'r') as f:
        ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        config.vifibnet = bin(ca.get_serial_number())[3:]

    # Get ip from cert.crt
    with open(config.cert, 'r') as f:
        cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        subject = cert.get_subject()
        prefix, prefix_len = subject.CN.split('/')
        config.internal_ip = ipFromPrefix(config.vifibnet, prefix, int(prefix_len))
        log('Intranet ip : %s' % (config.internal_ip,), 3)

    # Treat openvpn arguments
    if config.openvpn_args[0] == "--":
        del config.openvpn_args[0]
    config.openvpn_args.append('--ca')
    config.openvpn_args.append(config.ca)
    config.openvpn_args.append('--cert')
    config.openvpn_args.append(config.cert)

    log("Configuration completed", 1)
