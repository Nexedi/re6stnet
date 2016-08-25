#!/usr/bin/python2
import atexit, errno, logging, os, shutil, signal
import socket, struct, subprocess, sys, time, threading
from collections import deque
from functools import partial
if 're6st' not in sys.modules:
    sys.path[0] = os.path.dirname(os.path.dirname(sys.path[0]))
from re6st import plib, tunnel, utils, version, x509
from re6st.cache import Cache
from re6st.utils import exit, ReexecException

def getConfig():
    parser = utils.ArgParser(fromfile_prefix_chars='@',
        description="Resilient virtual private network application.")
    _ = parser.add_argument
    _('-V', '--version', action='version', version=version.version)

    _('--ip', action='append', default=[],
        help="IP address advertised to other nodes. Special values:\n"
             "- upnp: redirect ports when UPnP device is found\n"
             "- any: ask peers our IP\n"
             " (default: like 'upnp' if miniupnpc is installed,\n"
             "  otherwise like 'any')")
    _('--registry', metavar='URL', required=True,
        help="Public HTTP URL of the registry, for bootstrapping.")
    _('-l', '--log', default='/var/log/re6stnet',
        help="Path to the directory used for log files:\n"
             "- re6stnet.log: log file of re6stnet itself\n"
             "- babeld.log: log file of router\n"
             "- <iface>.log: 1 file per spawned OpenVPN\n")
    _('-r', '--run', default='/var/run/re6stnet',
        help="Path to re6stnet runtime directory:\n"
             "- babeld.pid (option -I of babeld)\n"
             "- babeld.sock (option -R of babeld)\n")
    _('-s', '--state', default='/var/lib/re6stnet',
        help="Path to re6stnet state directory:\n"
             "- cache.db: cache of network parameters and peer addresses\n"
             "- babeld.state: see option -S of babeld\n")
    _('-v', '--verbose', default=1, type=int, metavar='LEVEL',
        help="Log level of re6stnet itself. 0 disables logging. 1=WARNING,"
             " 2=INFO, 3=DEBUG, 4=TRACE. Use SIGUSR1 to reopen log."
             " See also --babel-verb and --verb for logs of spawned processes.")
    _('-i', '--interface', action='append', dest='iface_list', default=[],
        help="Extra interface for LAN discovery. Highly recommanded if there"
             " are other re6st node on the same network segment.")
    _('-I', '--main-interface', metavar='IFACE', default='lo',
        help="Set re6stnet IP on given interface. Any interface not used for"
             " tunnelling can be chosen.")
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

    _ = parser.add_argument_group('routing').add_argument
    _('-B', dest='babel_args', metavar='ARG', action='append', default=[],
        help="Extra arguments to forward to Babel.")
    _('-D', '--default', action='store_true',
        help="Access internet via this network (in this case, make sure you"
             " don't already have a default route), or if your kernel was"
             " compiled without support for source address based routing"
             " (CONFIG_IPV6_SUBTREES). Meaningless with --gateway.")
    _('--table', type=int, choices=(0,),
        help="DEPRECATED: Use --default instead of --table=0")
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
        choices=('none', 'udp', 'tcp', 'udp6', 'tcp6'), default=['udp', 'udp6'],
        help="Do never try to create tunnels using given protocols."
             " 'none' has precedence over other options.")
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

    if config.table is not None:
        logging.warning("--table option is deprecated: use --default instead")
        config.default = True
    if config.default and config.gateway:
        sys.exit("error: conflicting options --default and --gateway")

    if 'none' in config.disable_proto:
        config.disable_proto = ()
    if config.default:
        # Make sure we won't tunnel over re6st.
        config.disable_proto = tuple(set(('tcp6', 'udp6')).union(
            config.disable_proto))
    address = ()
    server_tunnels = {}
    forwarder = None
    if config.client:
        config.babel_args.append('re6stnet')
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
        def ip_changed(ip):
            for family, proto_list in ((socket.AF_INET, ('tcp', 'udp')),
                                       (socket.AF_INET6, ('tcp6', 'udp6'))):
                try:
                    socket.inet_pton(family, ip)
                    break
                except socket.error:
                    pass
            else:
                family = None
            return family, [(ip, str(port), proto) for port, proto in pp
                            if not family or proto in proto_list]
        if config.gw_list:
          gw_list = deque(config.gw_list)
          def remote_gateway(dest):
            gw_list.rotate()
            return gw_list[0]
        else:
          remote_gateway = None
        if len(config.ip) > 1:
            if 'upnp' in config.ip or 'any' in config.ip:
                sys.exit("error: argument --ip can be given only once with"
                         " 'any' or 'upnp' value")
            logging.info("Multiple --ip passed: note that re6st does nothing to"
                " make sure that incoming paquets are replied via the correct"
                " gateway. So without manual network configuration, this can"
                " not be used to accept server connections from multiple"
                " gateways.")
        if 'upnp' in config.ip or not config.ip:
            logging.info('Attempting automatic configuration via UPnP...')
            try:
                from re6st.upnpigd import Forwarder
                forwarder = Forwarder('re6stnet openvpn server')
            except Exception, e:
                if config.ip:
                    raise
                logging.info("%s: assume we are not NATed", e)
            else:
                atexit.register(forwarder.clear)
                for port, proto in pp:
                    forwarder.addRule(port, proto)
                ip_changed = forwarder.checkExternalIp
                address = ip_changed(),
        elif 'any' not in config.ip:
            address = map(ip_changed, config.ip)
            ip_changed = None
        for x in pp:
            server_tunnels.setdefault('re6stnet-' + x[1], x)
    else:
        ip_changed = remote_gateway = None

    def call(cmd):
        logging.debug('%r', cmd)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        if p.returncode:
            raise EnvironmentError("%r failed with error %u\n%s"
                                   % (' '.join(cmd), p.returncode, stderr))
        return stdout
    def ip4(object, *args):
        args = ['ip', '-4', object, 'add'] + list(args)
        call(args)
        args[3] = 'del'
        cleanup.append(lambda: subprocess.call(args))
    def ip(object, *args):
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
        config.babel_args += server_tunnels
        timeout = 4 * cache.hello
        cleanup = [lambda: cache.cacheMinimize(config.client_count),
                   lambda: shutil.rmtree(config.run, True)]
        utils.makedirs(config.run, 0700)
        control_socket = os.path.join(config.run, 'babeld.sock')
        if config.client_count and not config.client:
            tunnel_manager = tunnel.TunnelManager(control_socket,
                cache, cert, config.openvpn_args, timeout,
                config.client_count, config.iface_list, address, ip_changed,
                remote_gateway, config.disable_proto, config.neighbour)
            config.babel_args += tunnel_manager.new_iface_list
        else:
            tunnel_manager = tunnel.BaseTunnelManager(control_socket,
                cache, cert, address)
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
                for iface, (port, proto) in server_tunnels.iteritems():
                    r, x = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
                    cleanup.append(plib.server(iface, config.max_clients,
                        dh, x.fileno(), port, proto, cache.encrypt,
                        '--ping-exit', str(timeout), *config.openvpn_args,
                        preexec_fn=r.close).stop)
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
            if config.default:
                def check_no_default_route():
                    for route in call(('ip', '-6', 'route', 'show',
                                        'default')).splitlines():
                        if not (' proto babel ' in route
                             or ' proto 42 ' in route):
                            sys.exit("Detected default route (%s)"
                                " whereas you specified --default."
                                " Fix your configuration." % route)
                check_no_default_route()
                def check_no_default_route_thread():
                    try:
                        while True:
                            time.sleep(60)
                            try:
                                check_no_default_route()
                            except OSError, e:
                                if e.errno != errno.ENOMEM:
                                    raise
                    except:
                        utils.log_exception()
                    finally:
                        exit.kill_main(1)
                t = threading.Thread(target=check_no_default_route_thread)
                t.daemon = True
                t.start()
            ip('route', 'unreachable', my_network)

            config.babel_args += config.iface_list
            cleanup.append(plib.router((my_ip, len(subnet)), ipv4,
                None if config.gateway else
                '' if config.default else
                my_network, cache.hello,
                os.path.join(config.log, 'babeld.log'),
                os.path.join(config.state, 'babeld.state'),
                os.path.join(config.run, 'babeld.pid'),
                control_socket, cache.babel_default,
                *config.babel_args).stop)
            if config.up:
                exit.release()
                r = os.system(config.up)
                if r:
                    sys.exit(r)
                exit.acquire()
            for cmd in config.daemon or ():
                cleanup.insert(-1, utils.Popen(cmd, shell=True).stop)
            try:
                cleanup[-1:-1] = (tunnel_manager.delInterfaces,
                                  tunnel_manager.killAll)
            except AttributeError:
                pass
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
    except ReexecException, e:
        logging.info(e)
    except Exception:
        utils.log_exception()
        sys.exit(1)
    try:
        sys.exitfunc()
    finally:
        os.execvp(sys.argv[0], sys.argv)

if __name__ == "__main__":
    main()
