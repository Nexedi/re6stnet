#!/usr/bin/env python3
import http.client, logging, os, socket, sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingTCPServer
from urllib.parse import parse_qsl
if 're6st' not in sys.modules:
    sys.path[0] = os.path.dirname(os.path.dirname(sys.path[0]))
from re6st import registry, utils, version

# To generate server ca and key with serial for 2001:db8:42::/48
#  openssl req -nodes -new -x509 -key ca.key -set_serial 0x120010db80042 -days 3650 -out ca.crt

IPV6_V6ONLY = 26
SOL_IPV6 = 41


class RequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            try:
                path, query = self.path.split('?', 1)
            except ValueError:
                path = self.path
                query = {}
            else:
                query = dict(parse_qsl(query, keep_blank_values=True,
                                              strict_parsing=True))
            _, path = path.split('/')
            if not _:
                return self.server.handle_request(self, path, query)
        except Exception:
            logging.info(self.requestline, exc_info=True)
        self.send_error(HTTPStatus.BAD_REQUEST)

    def log_error(*args):
        pass


class HTTPServer4(ThreadingTCPServer):

    allow_reuse_address = True
    daemon_threads = True


class HTTPServer6(HTTPServer4):

    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(SOL_IPV6, IPV6_V6ONLY, 1)
        HTTPServer4.server_bind(self)


def main():
    parser = utils.ArgParser(fromfile_prefix_chars='@',
        description="re6stnet registry used to bootstrap nodes"
                    " and deliver certificates.")
    _ = parser.add_argument
    _('--port', type=int, default=80,
        help="Port on which the server will listen.")
    _('-4', dest='bind4', default='0.0.0.0',
        help="Bind server to this IPv4.")
    _('-6', dest='bind6', default='::',
        help="Bind server to this IPv6.")
    _('--db', default='/var/lib/re6stnet/registry.db',
        help="Path to SQLite database file. It is automatically initialized"
             " if the file does not exist.")
    _('--dh', required=True,
        help="File containing Diffie-Hellman parameters in .pem format."
             " To generate them, you can use something like:\n"
             "openssl dhparam -out dh2048.pem 2048")
    _('--ca', required=True, help=parser._ca_help)
    _('--key', required=True,
            help="CA private key in .pem format. For example:\nopenssl"
            " genpkey -out ca.key -algorithm rsa -pkeyopt rsa_keygen_bits:2048")
    _('--mailhost',
            help="SMTP host to send confirmation emails. For debugging"
                 " purpose, it can also be an absolute or existing path to"
                 " a mailbox file. If unset, registration by mail is disabled.")
    _('--smtp-user',
            help="SMTP login.")
    _('--smtp-pwd',
            help="SMTP password.")
    _('--smtp-starttls', action='store_true',
            help="Use STARTTLS for SMTP connections.")
    _('--prefix-length', default=16, type=int,
            help="Default length of allocated prefixes."
                 " If 0, registration by email is disabled.")
    _('--anonymous-prefix-length', type=int,
            help="Length of allocated anonymous prefixes."
                 " If 0 or unset, anonymous registration is disabled.")
    _('--ipv4', nargs=2, metavar=("IP/N", "PLEN"),
        help="Enable ipv4. Each node is assigned a subnet of length PLEN"
             " inside network IP/N.")
    _('-l', '--logfile', default='/var/log/re6stnet/registry.log',
            help="Path to logging file.")
    _('-r', '--run', default='/var/run/re6stnet',
        help="Path to re6stnet runtime directory:\n"
             "- babeld.sock (option -R of babeld)\n")
    _('-v', '--verbose', default=1, type=int,
            help="Log level. 0 disables logging. 1=WARNING, 2=INFO,"
                 " 3=DEBUG, 4=TRACE. Use SIGUSR1 to reopen log.")
    _('--min-protocol', default=version.min_protocol, type=int,
        help="Reject nodes that are too old. Current is %s." % version.protocol)
    _('--authorized-origin', action='append', default=['127.0.0.1', '::1'],
        help="Authorized IPs to access origin-restricted RPC.")
    _('--community',
        help="File containing community configuration. This file cannot be"
             " empty and must contain the default location ('*').")
    _('--grace-period', default=8640000, type=int,
        help="Period in seconds during which a client can renew its"
             " certificate even if expired (default 100 days)")

    _ = parser.add_argument_group('routing').add_argument
    _('--hello', type=int, default=15,
        help="Hello interval in seconds, for both wired and wireless"
             " connections. OpenVPN ping-exit option is set to 4 times the"
             " hello interval. It takes between 3 and 4 times the"
             " hello interval for Babel to re-establish connection with a"
             " node for which the direct connection has been cut.")

    _ = parser.add_argument_group('tunnelling').add_argument
    _('--encrypt', action='store_true',
        help='Specify that tunnels should be encrypted.')
    _('--client-count', default=10, type=int,
        help="Number of client tunnels to set up.")
    _('--max-clients', type=int,
        help="Maximum number of accepted clients per OpenVPN server. (default:"
             " client-count * 2, which actually represents the average number"
             " of tunnels to other peers)")
    _('--tunnel-refresh', default=300, type=int,
        help="Interval in seconds between two tunnel refresh: the worst"
             " tunnel is closed if the number of client tunnels has reached"
             " its maximum number (client-count).")
    _('--same-country', action='append', metavar="CODE",
        help="prevent tunnelling accross borders of listed countries")

    config = parser.parse_args()

    if not version.min_protocol <= config.min_protocol <= version.protocol:
        parser.error("--min-protocol: value must between %s and %s (included)"
                     % (version.min_protocol, version.protocol))

    if config.ipv4:
        ipv4, plen = config.ipv4
        try:
            ip, n = ipv4.split('/')
            config.ipv4 = "%s/%s" % (socket.inet_ntoa(socket.inet_aton(ip)),
                                     int(n)), int(plen)
        except (socket.error, ValueError):
            parser.error("invalid argument --ipv4")

    utils.setupLog(config.verbose, config.logfile)

    if config.max_clients is None:
        config.max_clients = config.client_count * 2

    server = registry.RegistryServer(config)
    def requestHandler(request, client_address, _):
        RequestHandler(request, client_address, server)

    server_dict = {}
    if config.bind4:
        r = HTTPServer4((config.bind4, config.port), requestHandler)
        server_dict[r.fileno()] = r._handle_request_noblock
    if config.bind6:
        r = HTTPServer6((config.bind6, config.port), requestHandler)
        server_dict[r.fileno()] = r._handle_request_noblock
    if server_dict:
        while True:
            args = server_dict.copy(), {}, []
            server.select(*args)
            utils.select(*args)


if __name__ == "__main__":
    main()
