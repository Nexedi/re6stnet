#!/usr/bin/env python3
import atexit, errno, logging, os, shutil, signal
import socket, struct, subprocess, sys
from collections import deque
from functools import partial
if 're6st' not in sys.modules:
    sys.path[0] = os.path.dirname(os.path.dirname(sys.path[0]))
from re6st import plib, tunnel, utils, version, x509
from re6st.cache import Cache
from re6st.utils import exit, ReexecException

DEFAULT_DISABLED_PROTO = ['udp', 'udp6']

def getConfig():
    parser = utils.ArgParser(fromfile_prefix_chars='@',
        description="Resilient virtual private network application.")
    _ = parser.add_argument
    _('-V', '--version', action='version', version=version.version)

    _('--ip', action='append', default=[],
        help="IP address advertised to other nodes.\n"
             "Special values for IPv4:\n"
             "- upnp: redirect ports when UPnP device is found\n"
             "- any: ask peers our IP\n"
             " (default: like 'upnp' if miniupnpc is installed,\n"
             "  otherwise like 'any')\n"
             "For IPv6, ask peers our IP if none given.")
    _('--registry', metavar='URL', required=True,
        help="Public HTTP URL of the registry, for bootstrapping.")
    _('-l', '--log', default='/var/log/re6stnet',
        help="Path to the directory used for log files:\n"
             "- re6stnet.log: log file of re6stnet itself\n"
             "- babeld.log: log file of router\n"
             "- <iface>.log: 1 file per spawned OpenVPN\n")
    _('-r', '--run', default='/var/run/re6stnet',
        help="Path to re6stnet runtime directory:\n"
             "- babeld.sock (option -R of babeld)\n")
    _('-s', '--state', default='/var/lib/re6stnet',
        help="Path to re6stnet state directory:\n"
             "- cache.db: cache of network parameters and peer addresses\n"
             "- babeld.state: see option -S of babeld\n")
    _('-v', '--verbose', default=2, type=int, metavar='LEVEL',
        help="Log level of re6stnet itself. 0 disables logging. 1=WARNING,"
             " 2=INFO, 3=DEBUG, 4=TRACE. Use SIGUSR1 to reopen log."
             " See also --babel-verb and --verb for logs of spawned processes.")
    _('-i', '--interface', action='append', dest='iface_list', default=[],
        help="Extra interface for LAN discovery. Highly recommended if there"
             " are other re6st nodes on the same network segment.")
    _('-I', '--main-interface', metavar='IFACE', default='lo',
        help="Set re6stnet IP on given interface. Any interface not used for"
             " tunnelling can be chosen.")
    _('-m', '--multicast', action='store_true',
        help="Enable multicast routing.")
    _('--up', metavar='CMD',
        help="Shell command to run after successful initialization.")
    _('--daemon', action='append', metavar='CMD',
        help="Same as --up, but run in background: the command will be killed"
             " at exit (with a TERM signal, followed by KILL 5 seconds later"
             " if process is still alive).")
    _('--test', metavar='EXPR',
        help="Exit after configuration parsing. Status code is the"
             " result of the given Python expression. For example:\n"
             "  main_interface != 'eth0'")
    _('--console', metavar='SOCK',
        help="Socket path to Python console that can be used to inspect or"
             " patch this process. Use:\n"
             "   socat - UNIX:<SOCK>\n"
             "to access it.")
    _('--country', metavar='CODE',
        help="Country code that is advertised to other nodes"
             "(default: country is resolved by the registry)")

    _ = parser.add_argument_group('routing').add_argument
    _('-B', dest='babel_args', metavar='ARG', action='append', default=[],
        help="Extra arguments to forward to Babel.")
    _('-D', '--default', action='store_true',
        help="This is an obsolete option and ignored.")
    _('--table', type=int, choices=(0,),
        help="This is an obsolete option and ignored.")
    _('--gateway', action='store_true',
        help="Act as a gateway for this network (the default route will be"
             " exported). Do never use it if you don't know what it means.")

    _ = parser.add_argument_group('tunnelling').add_argument
    _('-O', dest='openvpn_args', metavar='ARG', action='append', default=[],
        help="Extra arguments to forward to both server and client OpenVPN"
             " subprocesses. Often used to configure verbosity.")
    _('--ovpnlog', action='store_true',
        help="Tell each OpenVPN subprocess to log to a dedicated file.")
    _('--pp', nargs=2, action='append', metavar=('PORT', 'PROTO'),
        help="Port and protocol to be announced to other peers, ordered by"
             " preference. For each protocol (udp, tcp, udp6, tcp6), start one"
             " openvpn server on the first given port."
             " (default: --pp 1194 udp --pp 1194 tcp)")
    _('--dh',
        help="File containing Diffie-Hellman parameters in .pem format"
             " (default: DH from registry)")
    _('--ca', required=True, help=parser._ca_help)
    _('--cert', required=True,
        help="Local peer's signed certificate in .pem format."
             " Common name defines the allocated prefix in the network.")
    _('--key', required=True,
        help="Local peer's private key in .pem format.")
    _('--client-count', type=int,
        help="Number of client tunnels to set up."
             " (default: value from registry)")
    _('--max-clients', type=int,
        help="Maximum number of accepted clients per OpenVPN server."
             " (default: value from registry)")
    _('--remote-gateway', action='append', dest='gw_list',
        help="Force each tunnel to be created through one the given gateways,"
             " in a round-robin fashion.")
    _('--disable-proto', action='append',
        choices=('none', 'udp', 'tcp', 'udp6', 'tcp6'),
        help="Do never try to create tunnels using given protocols."
             " 'none' has precedence over other options."
             " (default: %r)" % DEFAULT_DISABLED_PROTO)
    _('--client', metavar='HOST,PORT,PROTO[;...]',
        help="Do not run any OpenVPN server, but only 1 OpenVPN client,"
             " with specified remotes. Any other option not required in this"
             " mode is ignored (e.g. client-count, max-clients, etc.)")
    _('--neighbour', metavar='CN', action='append', default=[],
        help="List of peers that should be reachable directly, by creating"
             " tunnels if necesssary.")

    return parser.parse_args()

def main():
    # Get arguments
    config = getConfig()
    cert = x509.Cert(config.ca, config.key, config.cert)
    config.openvpn_args += cert.openvpn_args

    if config.test:
        sys.exit(eval(config.test, None, config.__dict__))

    # Set logging
    utils.setupLog(config.verbose, os.path.join(config.log, 're6stnet.log'))

    logging.trace("Environment: %r", os.environ)
    logging.trace("Configuration: %r", config)
    utils.makedirs(config.state)
    db_path = os.path.join(config.state, 'cache.db')
    if config.ovpnlog:
        plib.ovpn_log = config.log

    exit.signal(0, signal.SIGINT, signal.SIGTERM)
    exit.signal(-1, signal.SIGHUP, signal.SIGUSR2)

    cache = Cache(db_path, config.registry, cert)
    network = cert.network

    if config.client_count is None:
        config.client_count = cache.client_count
    if config.max_clients is None:
        config.max_clients = cache.max_clients

    if config.disable_proto is None:
        config.disable_proto = DEFAULT_DISABLED_PROTO
    elif 'none' in config.disable_proto:
        config.disable_proto = ()

    x = ['ip', '-6', 'route', 'add', 'unreachable', '::/128', 'from', '::/128']
    has_ipv6_subtrees = not subprocess.call(x)
    if has_ipv6_subtrees:
        x[3] = 'del'
        subprocess.check_call(x)
    else:
        logging.warning(
            "Source address based routing is not enabled in your kernel"
            " (CONFIG_IPV6_SUBTREES). %s",
            "Assuming you don't merge several re6st networks so routes from"
            " other networks will be ignored." if config.gateway else
            "This node won't receive traffic to be routed to the internet."
            " Make sure you don't already have a default route.")
        # Make sure we won't tunnel over re6st.
        config.disable_proto = tuple({'tcp6', 'udp6'}.union(
            config.disable_proto))

    def add_tunnels(iface_list):
        for iface in iface_list:
            config.babel_args += '-C', 'interface %s type tunnel' % iface
        config.iface_list += iface_list
    address = []
    server_tunnels = {}
    forwarder = None
    if config.client:
        add_tunnels(('re6stnet',))
    elif config.max_clients:
        if config.pp:
            pp = [(int(port), proto) for port, proto in config.pp]
            for port, proto in pp:
                if proto in config.disable_proto:
                    sys.exit("error: conflicting options --disable-proto %s"
                             " and --pp %u %s" % (proto, port, proto))
        else:
            pp = [x for x in ((1194, 'udp'), (1194, 'tcp'))
                    if x[1] not in config.disable_proto]
        ipv4_any = []
        ipv6_any = []
        for x in pp:
            server_tunnels.setdefault('re6stnet-' + x[1], x)
            (ipv4_any if x[1] in ('tcp', 'udp') else ipv6_any).append(x)
        ipv4 = []
        ipv6 = []
        for ip in config.ip:
            if ip not in ('any', 'upnp'):
                try:
                    socket.inet_pton(socket.AF_INET, ip)
                except socket.error:
                    socket.inet_pton(socket.AF_INET6, ip)
                    ipv6.append(ip)
                    continue
            ipv4.append(ip)
        def ip_changed(ip):
            try:
                socket.inet_aton(ip)
            except socket.error:
                family = socket.AF_INET6
                pp = ipv6_any
            else:
                if forwarder:
                    return forwarder.checkExternalIp(ip)
                family = socket.AF_INET
                pp = ipv4_any
            return family, [(ip, str(port), proto) for port, proto in pp]
        if config.gw_list:
          gw_list = deque(config.gw_list)
          def remote_gateway(dest):
            gw_list.rotate()
            return gw_list[0]
        else:
          remote_gateway = None
        if len(ipv4) > 1:
            if 'upnp' in ipv4 or 'any' in ipv4:
                sys.exit("error: argument --ip can be given only once with"
                         " 'any' or 'upnp' value")
            logging.info("Multiple --ip passed: note that re6st does nothing to"
                " make sure that incoming paquets are replied via the correct"
                " gateway. So without manual network configuration, this can"
                " not be used to accept server connections from multiple"
                " gateways.")
        if 'upnp' in ipv4 or not ipv4:
            logging.info('Attempting automatic configuration via UPnP...')
            try:
                from re6st.upnpigd import Forwarder
                forwarder = Forwarder('re6stnet openvpn server')
            except Exception as e:
                if ipv4:
                    raise
                logging.info("%s: assume we are not NATed", e)
            else:
                atexit.register(forwarder.clear)
                for port, proto in ipv4_any:
                    forwarder.addRule(port, proto)
                address.append(forwarder.checkExternalIp())
        elif 'any' not in ipv4:
            address += map(ip_changed, ipv4)
            ipv4_any = ()
        if ipv6:
            address += map(ip_changed, ipv6)
            ipv6_any = ()
    else:
        ip_changed = remote_gateway = None

    def call(cmd):
        logging.debug('%r', cmd)
        return subprocess.run(cmd, capture_output=True, check=True).stdout
    def ip4(object: str, *args):
        args = ['ip', '-4', object, 'add'] + list(args)
        call(args)
        args[3] = 'del'
        cleanup.append(lambda: subprocess.call(args))
    def ip(object: str, *args):
        args = ['ip', '-6', object, 'add'] + list(args)
        call(args)
        args[3] = 'del'
        cleanup.append(lambda: subprocess.call(args))

    try:
        subnet = network + cert.prefix
        my_ip = utils.ipFromBin(subnet, '1')
        my_subnet = '%s/%u' % (utils.ipFromBin(subnet), len(subnet))
        my_network = "%s/%u" % (utils.ipFromBin(network), len(network))
        os.environ['re6stnet_ip'] = my_ip
        os.environ['re6stnet_iface'] = config.main_interface
        os.environ['re6stnet_subnet'] = my_subnet
        os.environ['re6stnet_network'] = my_network

        # Init db and tunnels
        add_tunnels(server_tunnels)
        timeout = 4 * cache.hello
        cleanup = [lambda: cache.cacheMinimize(config.client_count),
                   lambda: shutil.rmtree(config.run, True)]
        utils.makedirs(config.run, 0o700)
        control_socket = os.path.join(config.run, 'babeld.sock')
        if config.client_count and not config.client:
            tunnel_manager = tunnel.TunnelManager(control_socket,
                cache, cert, config.openvpn_args, timeout, config.client_count,
                config.iface_list, config.country, address, ip_changed,
                remote_gateway, config.disable_proto, config.neighbour)
            add_tunnels(tunnel_manager.new_iface_list)
        else:
            tunnel_manager = tunnel.BaseTunnelManager(control_socket,
                cache, cert, config.country, address)
        cleanup.append(tunnel_manager.sock.close)

        try:
            exit.acquire()

            ipv4 = getattr(cache, 'ipv4', None)
            if ipv4:
                serial = cert.subject_serial
                if cache.ipv4_sublen <= 16 and serial < 1 << cache.ipv4_sublen:
                    dot4 = lambda x: socket.inet_ntoa(struct.pack('!I', x))
                    ip4('route', 'unreachable', ipv4, 'proto', 'static')
                    ipv4, n = ipv4.split('/')
                    ipv4, = struct.unpack('!I', socket.inet_aton(ipv4))
                    n = int(n) + cache.ipv4_sublen
                    x = ipv4 | serial << 32 - n
                    ipv4 = dot4(x | (n < 31))
                    config.openvpn_args += '--ifconfig', \
                        ipv4, dot4((1<<32) - (1<<32-n))
                    if not isinstance(tunnel_manager, tunnel.TunnelManager):
                        ip4('addr', ipv4, 'dev', config.main_interface)
                        if config.main_interface == "lo":
                            ip4('route', 'unreachable', "%s/%s" % (dot4(x), n),
                                'proto', 'static')
                    ipv4 = ipv4, n
                else:
                    logging.warning(
                        "IPv4 payload disabled due to wrong network parameters")
                    ipv4 = None

            if os.uname()[2] < '2.6.40': # BBB
                logging.warning("Fallback to ip-addrlabel because Linux < 3.0"
                    " does not support RTA_PREFSRC for ipv6. Note however that"
                    " this workaround does not work with extra interfaces that"
                    " already have a public IP")
                ip('addrlabel', 'prefix', my_network, 'label', '99')
                # No need to tell babeld not to set a preferred source IP in
                # installed routes. The kernel will silently discard the option.
            R = {}
            if config.client:
                address_list = [x for x in utils.parse_address(config.client)
                                  if x[2] not in config.disable_proto]
                if not address_list:
                    sys.exit("error: --disable_proto option disables"
                             " all addresses given by --client")
                cleanup.append(plib.client('re6stnet',
                    address_list, cache.encrypt, '--ping-restart',
                    str(timeout), *config.openvpn_args).stop)
            elif server_tunnels:
                dh = config.dh
                if not dh:
                    dh = os.path.join(config.state, "dh.pem")
                    cache.getDh(dh)
                for iface, (port, proto) in server_tunnels.items():
                    r, x = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
                    utils.setCloexec(r)
                    cleanup.append(plib.server(iface, config.max_clients,
                        dh, x.fileno(), port, proto, cache.encrypt,
                        '--ping-exit', str(timeout), *config.openvpn_args).stop)
                    R[r] = partial(tunnel_manager.handleServerEvent, r)
                    x.close()

            ip('addr', my_ip + '/%s' % len(subnet),
               'dev', config.main_interface)
            if_rt = ['ip', '-6', 'route', 'del',
                     'fe80::/64', 'dev', config.main_interface]
            if config.main_interface == 'lo':
                # WKRD: Removed this useless route now, since the kernel does
                #       not even remove it on exit.
                subprocess.call(if_rt)
            if_rt[4] = my_subnet
            cleanup.append(lambda: subprocess.call(if_rt))
            ip('route', 'unreachable', my_network)

            config.babel_args += config.iface_list
            cleanup.append(plib.router((my_ip, len(subnet)), ipv4,
                (my_network, config.gateway, has_ipv6_subtrees),
                cache.hello,
                os.path.join(config.log, 'babeld.log'),
                os.path.join(config.state, 'babeld.state'),
                control_socket, cache.babel_default,
                tuple(getattr(cache, k, None) for k in
                      ('babel_hmac_sign', 'babel_hmac_accept')),
                *config.babel_args).stop)
            if config.up:
                exit.release()
                r = os.system(config.up)
                if r:
                    sys.exit(r)
                exit.acquire()
            # Keep babeld cleanup at the end, so that babeld is stopped first,
            # which gives a chance to send wildcard retractions.
            for cmd in config.daemon or ():
                cleanup.insert(-1, utils.Popen(cmd, shell=True).stop)
            cleanup.insert(-1, tunnel_manager.close)
            if config.console:
                from re6st.debug import Console
                def console(socket, frame=sys._getframe()):
                    try:
                        import pdb; pdb.Pdb(stdin=socket,
                                            stdout=socket).set_trace()
                        frame.f_locals # main() locals
                    finally:
                        socket.close()
                console = Console(config.console, console)
                cleanup.append(console.close)

            # main loop
            exit.release()
            select_list = [forwarder.select] if forwarder else []
            if config.console:
                select_list.append(console.select)
            if config.multicast:
                from re6st.multicast import PimDm
                pimdm = PimDm()
                cleanup.append(pimdm.run(config.iface_list, config.run).stop)
                select_list.append(pimdm.select)
            select_list += tunnel_manager.select, utils.select
            while True:
                args = R.copy(), {}, []
                for s in select_list:
                    s(*args)
        finally:
            # XXX: We have a possible race condition if a signal is handled at
            #      the beginning of this clause, just before the following line.
            exit.acquire(0) # inhibit signals
            while cleanup:
                try:
                    cleanup.pop()()
                except:
                    pass
            exit.release()
    except ReexecException as e:
        logging.info(e)
    except Exception:
        utils.log_exception()
        sys.exit(1)
    try:
        atexit._run_exitfuncs()
    finally:
        os.execvp(sys.argv[0], sys.argv)

if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if type(e.code) is str:
            if hasattr(logging, 'trace'): # utils.setupLog called
                logging.critical(e.code)
        raise
