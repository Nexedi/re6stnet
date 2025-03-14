import errno, json, logging, os, platform, random, socket
import subprocess, struct, sys, time, weakref
from collections import defaultdict, deque
from bisect import bisect, insort
from collections.abc import Iterator, Sequence
from typing import Callable, TYPE_CHECKING

from OpenSSL import crypto
from . import plib, routing, utils, version, x509
if TYPE_CHECKING:
    from . import cache

PORT = 326
NETCONF_CHECK = 3600

family_dict = {
    socket.AF_INET: 'IPv4',
    socket.AF_INET6: 'IPv6',
}

proto_dict = {
    'tcp4': (socket.AF_INET, socket.SOL_TCP),
    'udp4': (socket.AF_INET, socket.SOL_UDP),
    'tcp6': (socket.AF_INET6, socket.SOL_TCP),
    'udp6': (socket.AF_INET6, socket.SOL_UDP),
}
proto_dict['tcp'] = proto_dict['tcp4']
proto_dict['udp'] = proto_dict['udp4']

def resolve(ip, port, proto: str) \
        -> tuple[socket.AddressFamily | None, Iterator[str]]:
    try:
        family, proto = proto_dict[proto]
    except KeyError:
        return None, ()
    return family, (x[-1][0]
        for x in socket.getaddrinfo(ip, port, family, 0, proto))

class MultiGatewayManager(dict):

    def __init__(self, gateway: Callable[[str], str]):
        self._gw = gateway

    def _route(self, cmd: str, dest: str, gw: str):
        if gw:
            cmd = 'ip', '-4', 'route', cmd, '%s/32' % dest, 'via', gw
            logging.trace('%r', cmd)
            subprocess.check_call(cmd)

    def add(self, dest: str, route: bool):
        try:
            self[dest][1] += 1
        except KeyError:
            gw = self._gw(dest) if route else None
            self[dest] = [gw, 0]
            self._route('add', dest, gw)

    def remove(self, dest: str):
        gw, count = self[dest]
        if count:
            self[dest][1] = count - 1
        else:
            del self[dest]
            try:
                self._route('del', dest, gw)
            except:
                pass

class Connection:

    _retry = 0
    serial = None
    time = float('inf')

    def __init__(self, tunnel_manager: "TunnelManager",
                 address_list, iface, prefix):
        self.tunnel_manager = tunnel_manager
        self.address_list = address_list
        self.iface = iface
        self._prefix = prefix

    def __iter__(self):
        if not hasattr(self, '_remote_ip_set'):
            self._remote_ip_set = set()
            for ip, port, proto in self.address_list:
                try:
                    socket.inet_pton(socket.AF_INET, ip)
                except socket.error:
                    continue
                self._remote_ip_set.add(ip)
        return iter(self._remote_ip_set)

    def open(self):
        tm = self.tunnel_manager
        self.time = time.time()
        self.process = plib.client(
            self.iface, (self.address_list[self._retry],), tm.encrypt,
            '--verify-x509-name',
                '%u/%u' % (int(self._prefix, 2), len(self._prefix)), 'name',
            '--resolv-retry', '0',
            '--connect-retry-max', '3', '--tls-exit',
            '--remap-usr1', 'SIGTERM',
            '--ping-exit', str(tm.timeout),
            '--route-up', '%s %u' % (plib.ovpn_client, tm.write_sock.fileno()),
            *tm.ovpn_args, pass_fds=[tm.write_sock.fileno()])
        tm.resetTunnelRefresh()
        self._retry += 1

    def connected(self, serial):
        cache = self.tunnel_manager.cache
        if serial in cache.crl:
            self.tunnel_manager._kill(self._prefix)
            return
        self.serial = serial
        i = self._retry - 1
        self._retry = None
        if i:
            cache.addPeer(self._prefix, ','.join(self.address_list[i]), True)
        else:
            cache.connecting(self._prefix, False)

    def close(self):
        try:
            self.process.stop()
        except AttributeError:
            pass

    def refresh(self):
        # Check that the connection is alive
        if self.process.poll() is not None:
            logging.info('Connection with %s/%s has failed with return code %s',
                         int(self._prefix, 2), len(self._prefix),
                         self.process.returncode)
            if self._retry is None:
                return 1
            if len(self.address_list) <= self._retry:
                return -1
            logging.info('Retrying with alternate address')
            self.close()
            self.open()
        return 0

class TunnelKiller:

    state = None

    def __init__(self, peer, tunnel_manager, client=False):
        self.peer = peer
        self.tm = weakref.proxy(tunnel_manager)
        self.timeout = time.time() + 2 * tunnel_manager.timeout
        self.client = client
        self()

    def __repr__(self):
        return '<%s state=%s client=%s timeout=%s>' % (
            self.__class__.__name__,
            self.state,
            self.client,
            self.timeout)

    def __call__(self):
        if self.state:
            return getattr(self, self.state)()
        tm_routing = self.tm.routing
        try:
            neigh = tm_routing.neighbours[self.peer][0]
        except KeyError:
            return
        self.state = 'softLocking'
        tm_routing.send(routing.SetCostMultiplier(
            neigh.address, neigh.ifindex, 4096))
        self.address = neigh.address
        self.ifindex = neigh.ifindex
        self.cost_multiplier = neigh.cost_multiplier

    def softLocking(self):
        tm = self.tm
        if self.peer in tm.routing.neighbours or None in tm.routing.neighbours:
            return
        tm.routing.send(routing.SetCostMultiplier(
            self.address, self.ifindex, 0))
        self.state = "hardLocking"

    def hardLocking(self):
        tm = self.tm
        if (self.address, self.ifindex) in tm.routing.locked:
            self.state = 'locked'
            self.timeout = time.time() + 2 * tm.timeout
            tm.sendto(self.peer, b'\2' if self.client else b'\3')
        else:
            self.timeout = 0

    def unlock(self):
        if self.state:
            self.tm.routing.send(routing.SetCostMultiplier(
                self.address, self.ifindex, self.cost_multiplier))

    def abort(self):
        if self.state != 'unlocking':
            self.state = 'unlocking'
            self.timeout = time.time() + 2 * self.tm.timeout

    locked = unlocking = lambda _: None


class BaseTunnelManager:

    # TODO: To minimize downtime when network parameters change, we should do
    #       our best to not restart any process. Ideally, this list should be
    #       empty and the affected subprocesses reloaded.
    NEED_RESTART = frozenset(('babel_default', 'babel_hmac_accept',
                              'babel_hmac_sign', 'encrypt',
                              'hello', 'ipv4', 'ipv4_sublen'))

    _geoiplookup = None
    _forward = None

    def __init__(self, control_socket, cache: "cache.Cache", cert: x509.Cert,
                 conf_country, address=()):
        self.cert = cert
        self._network = cert.network
        self._prefix = cert.prefix
        self.cache = cache
        self._connecting = set()
        self._connection_dict = {}
        self._served = defaultdict(dict)
        self._version = cache.version
        self._conf_country = conf_country

        address_dict = defaultdict(list)
        for family, address in address:
            address_dict[family] += address

        # Cache may contain our country, we want to use it if possible to
        # prevent interaction with registry
        cache_address = cache.my_address
        if cache_address:
            cache_dict = defaultdict(list)
            for address in utils.parse_address(cache_address):
                try:
                    proto = proto_dict[address[2]]
                except KeyError:
                    continue
                cache_dict[proto[0]].append(address)
            if {proto: cache_dict[proto][:3] for proto in cache_dict
               } == address_dict:
                address_dict = cache_dict

        db = os.getenv('GEOIP2_MMDB')
        if db:
            from geoip2 import database, errors
            country = database.Reader(db).country
            def geoiplookup(ip):
                try:
                    return country(ip).country.iso_code.encode()
                except Exception:
                    return
            self._geoiplookup = geoiplookup
        if cache.same_country:
            self._country = {}

            address_dict = {family: self._updateCountry(address)
                            for family, address in address_dict.items()}
        elif cache.same_country:
            sys.exit("Can not respect 'same_country' network configuration"
                     " (GEOIP2_MMDB not set)")
        self._address = {family: utils.dump_address(address)
                         for family, address in address_dict.items()
                         if address}
        cache.my_address = ';'.join(self._address.values())

        self.sock = socket.socket(socket.AF_INET6,
            socket.SOCK_DGRAM | socket.SOCK_CLOEXEC)
        # See also http://stackoverflow.com/questions/597225/
        # about binding and anycast.
        self.sock.bind(('::', PORT))

        p = x509.Peer(self._prefix)
        p.stop_date = cache.next_renew
        self._peers = [p]
        self._timeouts = [(p.stop_date, self.invalidatePeers)]

        self.routing = routing.Babel(
            control_socket, weakref.proxy(self), self._network)

        now = self._next_refresh = time.time()
        self._maybe_old_version = None is not cache.valid_until < now

    def close(self):
        self.sock.close()
        self.routing.close()

    def select(self, r, w, t):
        r[self.sock] = self.handlePeerEvent
        t += self._timeouts
        if self._next_refresh:
            t.append((self._next_refresh, self.refresh))
        self.routing.select(r, w, t)

    def refresh(self):
        self._next_refresh = None
        if self._prefix != self.cache.registry_prefix:
            self.__request_dump('check_netconf')

    def __request_dump(self, reason):
        try:
            requesting_dump = self.__requesting_dump
        except AttributeError:
            requesting_dump = self.__requesting_dump = set()
        request = not requesting_dump
        requesting_dump.add(reason)
        if request:
            self.routing.request_dump()

    def babel_dump(self):
        for x in self.__requesting_dump:
            getattr(self, '_babel_dump_' + x)()
        self.__requesting_dump.clear()

    def selectTimeout(self, next, callback, force=True):
        t = self._timeouts
        for i, x in enumerate(t):
            if x[1] == callback:
                if not next:
                    logging.debug("timeout: removing %r (%s)",
                                  callback.__name__, next)
                    del t[i]
                elif force or next < x[0]:
                    logging.debug("timeout: updating %r (%s)",
                                  callback.__name__, next)
                    t[i] = next, callback
                return
        if next:
            logging.debug("timeout: adding %r (%s)", callback.__name__, next)
            t.append((next, callback))

    def invalidatePeers(self):
        next = float('inf')
        now = time.time()
        remove = []
        for i, peer in enumerate(self._peers):
            if peer.stop_date < now:
                if peer.prefix == self._prefix:
                    raise utils.ReexecException("Restart to renew certificate")
                remove.append(i)
            elif peer.stop_date < next:
                next = peer.stop_date
        for i in reversed(remove):
            del self._peers[i]
        self.selectTimeout(next, self.invalidatePeers)

    def _getPeer(self, prefix):
        return self._peers[bisect(self._peers, prefix) - 1]

    def sendto(self, prefix: str, msg):
        to = utils.ipFromBin(self._network + prefix), PORT
        peer = self._getPeer(prefix)
        if peer.prefix != prefix:
            peer = x509.Peer(prefix)
            insort(self._peers, peer)
        elif peer.connected:
            if msg is None:
                return
            return self._sendto(to, msg, peer)
        msg = peer.hello0(self.cert.cert)
        if msg and self._sendto(to, msg):
            peer.hello0Sent()

    def _sendto(self, to, msg, peer=None):
        if type(msg) is str:
            msg = msg.encode()
        try:
            r = self.sock.sendto(peer.encode(msg) if peer else msg, to)
        except socket.error as e:
            (logging.info if e.errno == errno.ENETUNREACH else logging.error)(
                'Failed to send message to %s (%s)', to, e)
            return
        if r and peer and msg:
            peer.sent()
        return r

    def handlePeerEvent(self):
        msg, address = self.sock.recvfrom(1<<16)
        to = address[:2]
        if address[0] == '::1':
            try:
                prefix, msg = msg.split(b'\0', 1)
                prefix = prefix.decode()
                int(prefix, 2)
            except ValueError:
                return
            if msg:
                self._forward = to
                code = msg[0]
                if prefix == self._prefix:
                    msg = self._processPacket(msg)
                    if msg:
                        self._sendto(to,
                                     b'%s\0%c%s' % (prefix.encode(), code, msg))
                else:
                    self.sendto(prefix, bytes([code | 0x80]) + msg[1:])
            return
        try:
            sender = utils.binFromIp(address[0])
        except socket.error:
            return # inet_pton does not parse '<ipv6>%<iface>'
        if len(msg) <= 4 or not sender.startswith(self._network):
            return
        prefix = sender[len(self._network):]
        peer = self._getPeer(prefix)
        msg = peer.decode(msg)
        if type(msg) is tuple:
          seqno, msg, protocol = msg
          def handleHello(peer, seqno, msg: bytes, retry):
            if seqno == 2:
                i = len(msg) // 2
                h = msg[:i]
                try:
                    peer.verify(msg[i:], h)
                    peer.newSession(self.cert.decrypt(h), protocol)
                except (AttributeError, x509.InvalidSignature,
                        x509.NewSessionError, subprocess.CalledProcessError):
                    logging.debug('ignored new session key from %r',
                                  address, exc_info=True)
                    return
                peer.version = self._version \
                    if self._sendto(to, b'\0' + self._version, peer) else b''
                return
            if seqno:
                h = x509.fingerprint(self.cert.cert).digest()
                seqno = msg.startswith(h)
                msg = msg[len(h):]
            try:
                cert = self.cert.loadVerify(msg,
                    True, crypto.FILETYPE_ASN1)
                stop_date = x509.notAfter(cert)
                serial = cert.get_serial_number()
                if serial in self.cache.crl:
                    raise ValueError("revoked")
            except (x509.VerifyError, ValueError) as e:
                if retry:
                    return True
                logging.debug('ignored invalid certificate from %r (%s)',
                              address, e.args[-1])
                return
            p = utils.binFromSubnet(x509.subnetFromCert(cert))
            if p != peer.prefix:
                if not prefix.startswith(p):
                    logging.debug('received %s/%s cert from wrong source %r',
                                  int(p, 2), len(p), address)
                    return
                peer = x509.Peer(p)
                insort(self._peers, peer)
            peer.cert = cert
            peer.cert_crypto = x509.load_der_x509_certificate(msg)
            peer.serial = serial
            peer.stop_date = stop_date
            self.selectTimeout(stop_date, self.invalidatePeers, False)
            if seqno:
                self._sendto(to, peer.hello(self.cert, protocol))
            else:
                msg = peer.hello0(self.cert.cert)
                if msg and self._sendto(to, msg):
                    peer.hello0Sent()
          if handleHello(peer, seqno, msg, seqno):
            # It is possible to reconstruct the original message because
            # the serialization of the protocol version is always unique.
            msg = utils.packInteger(protocol) + msg
            protocol = 0
            handleHello(peer, seqno, msg, False)
        elif msg:
            # We got a valid and non-empty message. Always reply
            # something so that the sender knows we're still connected.
            answer = self._processPacket(msg, peer.prefix)
            self._sendto(to, msg[0:1] + answer if answer else b'', peer)

    def _processPacket(self, msg: bytes, peer: x509.Peer|str=None):
        c = msg[0]
        msg = msg[1:]
        code = c & 0x7f
        if c > 0x7f and msg:
            if peer and self._forward:
                self._sendto(self._forward,
                             b'%s\0%c%s' % (peer.encode(), code, msg))
        elif code == 1: # address
            if msg:
                if peer:
                    msg = msg.decode()
                    self.cache.addPeer(peer, msg)
                    try:
                        self._connecting.remove(peer)
                    except KeyError:
                        return
                    self._makeTunnel(peer, msg)
            else:
                return ';'.join(
                    (','.join(a.split(',')[:3]) for a in
                        ';'.join(self._address.values()).split(';'))
                    if peer and
                        # Don't send country to old nodes
                        self._getPeer(peer).protocol < 7 else
                    self._address.values()).encode()
        elif not code: # network version
            if peer:
                try:
                    if msg == self._version:
                        return
                    self.cert.verifyVersion(msg)
                except x509.VerifyError:
                    pass
                else:
                    if msg < self._version:
                        return self._version
                    self._version = msg
                    self.selectTimeout(time.time() + 1, self.newVersion)
                finally:
                    if peer:
                        self._getPeer(peer).version = self._version
            else:
                self.selectTimeout(time.time() + 1, self.newVersion)
        elif code <= 3: # kill
            if peer:
                try:
                    tunnel_killer = self._killing[peer]
                except AttributeError:
                    pass
                except KeyError:
                    if code == 2 and peer in self._served: # request
                        self._killing[peer] = TunnelKiller(peer, self)
                else:
                    if code == 3 and tunnel_killer.state == 'locked': # response
                        self._kill(peer)
        elif code == 4: # node information
            if not msg:
                return ("%s, %s" % (version.version,
                                    platform.platform())).encode()
        elif code == 5:
            # the registry wants to know the topology for debugging purpose
            if not peer or peer == self.cache.registry_prefix:
                return (str(len(self._connection_dict)) + ''.join(
                    ' %s/%s' % (int(x, 2), len(x))
                    for x in (self._connection_dict, self._served)
                    for x in x)).encode()
        elif code == 7:
            # XXX: Quick'n dirty way to log in a common place.
            if peer and self._prefix == self.cache.registry_prefix:
                logging.info("%s/%s: %s", int(peer, 2), len(peer), msg)

    @staticmethod
    def _restart():
        raise utils.ReexecException(
            "Restart with new network parameters")

    def _babel_dump_check_netconf(self):
        now = time.time()
        self._next_refresh = now + NETCONF_CHECK
        peers = {prefix
            for neigh_routes in self.routing.neighbours.values()
            for prefix in neigh_routes[1]
            if prefix}
        maybe_old_version = (lambda: None is not self.cache.valid_until < now
            ) if self.cache.registry_prefix in peers else lambda: True
        if maybe_old_version():
            if not self._maybe_old_version:
                self._maybe_old_version = True
                return
            self.newVersion(False)
        self._maybe_old_version = maybe_old_version()

    def _babel_dump_new_version(self):
        for prefix in self.routing.neighbours:
            if prefix:
                peer = self._getPeer(prefix)
                if peer.prefix != prefix:
                    self.sendto(prefix, None)
                elif (peer.version < self._version and
                      self.sendto(prefix, b'\0' + self._version)):
                    peer.version = self._version

    def broadcastNewVersion(self):
        self.__request_dump('new_version')

    def newVersion(self, retry=True):
        changed = self.cache.updateConfig()
        if changed is None:
            if retry:
                logging.info(
                    "will retry to update network parameters in 5 minutes")
                self.selectTimeout(time.time() + 300, self.newVersion)
            return
        logging.info("changed: %r", sorted(changed))
        self.selectTimeout(None, self.newVersion)
        if not changed:
            return
        self._version = self.cache.version
        self.broadcastNewVersion()
        self.cache.warnProtocol()
        crl = self.cache.crl
        for i in reversed([i for i, peer in enumerate(self._peers)
                             if peer.serial in crl]):
            del self._peers[i]
        if self.cert.cert.get_serial_number() in crl:
            raise utils.ReexecException("Our certificate has just been revoked."
                " Let's try to renew it.")
        if (not self.NEED_RESTART.isdisjoint(changed)
            or version.protocol < self.cache.min_protocol
            # TODO: With --management, we could kill clients without restarting.
            or not all(crl.isdisjoint(serials.values())
                       for serials in self._served.values())):
            # Wait at least 1 second to broadcast new version to neighbours.
            self.selectTimeout(time.time() + 1 + self.cache.delay_restart,
                               self._restart)

    def handleServerEvent(self, sock: socket.socket):
        event, args = eval(sock.recv(65536))
        logging.debug("%s%r", event, args)
        r = getattr(self, '_ovpn_' + event.replace('-', '_'))(*args)
        if r is not None:
            sock.send(bytes([r]))

    def _ovpn_client_connect(self, common_name, iface, serial, trusted_ip):
        if serial in self.cache.crl:
            return False
        prefix = utils.binFromSubnet(common_name)
        self._served[prefix][iface] = serial
        if isinstance(self, TunnelManager): # XXX
            if self._gateway_manager is not None:
                self._gateway_manager.add(trusted_ip, False)
            if prefix in self._connection_dict and self._prefix < prefix:
                self._kill(prefix)
                self.cache.connecting(prefix, False)
        return True

    def _ovpn_client_disconnect(self, common_name, iface, serial, trusted_ip):
        prefix = utils.binFromSubnet(common_name)
        serials = self._served.get(prefix)
        try:
            del serials[iface]
        except (KeyError, TypeError):
            logging.exception("ovpn_client_disconnect%r",
                              (common_name, iface, serial, trusted_ip))
            return
        if not serials:
            del self._served[prefix]
        if isinstance(self, TunnelManager): # XXX
            self._abortTunnelKiller(prefix, iface)
            if self._gateway_manager is not None:
                self._gateway_manager.remove(trusted_ip)

    def _updateCountry(self, address):
        def update():
            for a in address:
                family, ip = resolve(*a[:3])
                for ip in ip:
                    country = a[3] if len(a) > 3 else self.cache.getCountry(ip)
                    if country:
                        if self._country.get(family) != country:
                            self._country[family] = country
                            logging.info('%s country: %s (%s)',
                                family_dict[family], country, ip)
                        return country
        country = self._conf_country or update()
        return [a[:3] + (country,) for a in address] if country else address

class TunnelManager(BaseTunnelManager):

    NEED_RESTART = BaseTunnelManager.NEED_RESTART.union((
        'client_count', 'max_clients', 'same_country', 'tunnel_refresh'))

    def __init__(self, control_socket, cache, cert, openvpn_args,
                 timeout, client_count, iface_list, conf_country, address,
                 ip_changed, remote_gateway: Callable[[str], str],
                 disable_proto: Sequence[str], neighbour_list=()):
        super().__init__(control_socket, cache, cert, conf_country, address)
        self.ovpn_args = openvpn_args
        self.timeout = timeout
        self._read_sock, self.write_sock = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_DGRAM)
        utils.setCloexec(self._read_sock)
        self._disconnected = 0
        self._distant_peers = []
        self._iface_to_prefix = {}
        self._iface_list = iface_list
        self._ip_changed = ip_changed
        self._gateway_manager = MultiGatewayManager(remote_gateway) \
                                if remote_gateway else None
        self._disable_proto = disable_proto
        self._neighbour_set = set(map(utils.binFromSubnet, neighbour_list))
        self._killing = {}

        self.resetTunnelRefresh()

        self._client_count = client_count
        self.new_iface_list = deque('re6stnet' + str(i)
            for i in range(1, self._client_count + 1))
        self._free_iface_list = []
        self._next_netconf_check = float('inf') \
            if self._prefix == cache.registry_prefix else self._next_refresh
        self._next_refresh = time.time()

    def close(self):
        self.killAll()
        self.delInterfaces()
        self._read_sock.close()
        self.write_sock.close()
        super().close()

    @property
    def encrypt(self):
        return self.cache.encrypt

    def resetTunnelRefresh(self):
        self._next_tunnel_refresh = time.time() + self.cache.tunnel_refresh

    def _tuntap(self, iface=None):
        if iface:
            self.new_iface_list.appendleft(iface)
            action = '--rmtun'
        else:
            iface = self.new_iface_list.popleft()
            action = '--mktun'
        # BBB: do not use 'ip tuntap' which is not available on old dists
        args = ('openvpn', action, '--verb', '0',
                '--dev', iface, '--dev-type', 'tap')
        logging.debug('%r', args)
        subprocess.check_call(args)
        return iface

    def delInterfaces(self):
        iface_list = self._free_iface_list
        iface_list += self._iface_to_prefix
        self._iface_to_prefix.clear()
        while iface_list:
          self._tuntap(iface_list.pop())

    def _getFreeInterface(self, prefix):
        try:
            iface = self._free_iface_list.pop()
        except IndexError:
            iface = self._tuntap()
        self._iface_to_prefix[iface] = prefix
        return iface

    def freeInterface(self, iface):
        self._free_iface_list.append(iface)
        del self._iface_to_prefix[iface]

    def select(self, r, w, t):
        super().select(r, w, t)
        r[self._read_sock] = self.handleClientEvent

    def refresh(self):
        logging.debug('Checking tunnels...')
        if self._cleanDeads() or \
           self._next_tunnel_refresh < time.time() or \
           self._killing or \
           self._makeNewTunnels(False):
            self._next_refresh = None
            # At startup, the following line calls babel_dump immediately.
            self.routing.request_dump()
        else:
            self._next_refresh = time.time() + 5

    def babel_dump(self):
        t = time.time()
        if self._next_netconf_check < t:
            self._babel_dump_check_netconf()
            self._next_netconf_check = self._next_refresh
        logging.debug('babel_dump: self._killing=%r', self._killing)
        if self._killing:
            for prefix, tunnel_killer in list(self._killing.items()):
                if tunnel_killer.timeout < t:
                    if tunnel_killer.state != 'unlocking':
                        logging.info(
                            'Abort destruction of tunnel %s %s/%s (state: %s)',
                            'to' if tunnel_killer.client else 'from',
                            int(prefix, 2), len(prefix), tunnel_killer.state)
                    tunnel_killer.unlock()
                    del self._killing[prefix]
                else:
                    tunnel_killer()
        remove = self._next_tunnel_refresh < t
        if remove:
            self._removeSomeTunnels()
            self.resetTunnelRefresh()
            self.cache.log()
        self._makeNewTunnels(True)
        # XXX: Commented code is an attempt to clean up unused interfaces
        #      but babeld does not leave ipv6 membership for deleted taps,
        #      causing a memory leak in the kernel (capped by sysctl
        #      net.core.optmem_max), and after some time, new neighbours fail
        #      to see each other.
        #if remove and len(self._connecting) < len(self._free_iface_list):
        #    self._tuntap(self._free_iface_list.pop())
        self._next_refresh = time.time() + 5

    def _cleanDeads(self):
        disconnected = False
        for prefix in list(self._connection_dict):
            status = self._connection_dict[prefix].refresh()
            if status:
                disconnected |= status > 0
                self._kill(prefix)
        return disconnected

    def _tunnelScore(self, prefix):
        # First try to not kill a persistent tunnel (see --neighbour option).
        # Then sort by the number of routed nodes.
        n = 0
        try:
            for x in self.routing.neighbours[prefix][1]:
                # Ignore the default route, which is redundant with the
                # border gateway node.
                if x:
                    n += 1
        except KeyError:
            # XXX: The route for this neighbour is not direct. In this case,
            #      a KeyError was raised because babeld dump doesn't give us
            #      enough information to match the neighbour prefix with its
            #      link-local address. This is a good candidate (so we return
            #      ()), but for the same reason, such tunnel can't be killed.
            #      In order not to remain indefinitely in a state where we
            #      never delete any tunnel because we would always select an
            #      unkillable one, we should return an higher score.
            pass
        return (prefix in self._neighbour_set, n) if n else ()

    def _removeSomeTunnels(self):
        # Get the candidates to killing
        peer_set = set(self._connection_dict)
        peer_set.difference_update(self._killing)
        # Keep only a small number of tunnels if server is not reachable
        # (user should configure NAT properly).
        if (self._client_count if self._served or self._disconnected else
              min(2, self._client_count)) <= len(peer_set) and \
           peer_set != self._neighbour_set:
            prefix = min(peer_set, key=self._tunnelScore)
            self._killing[prefix] = TunnelKiller(prefix, self, True)

    def _abortTunnelKiller(self, prefix, iface=None):
        tunnel_killer = self._killing.get(prefix)
        if tunnel_killer:
            if tunnel_killer.state:
                if not iface or \
                   iface == self.routing.interfaces[tunnel_killer.ifindex]:
                    tunnel_killer.abort()
            else:
                del self._killing[prefix]

    def _kill(self, prefix):
        logging.info('Killing the connection with %u/%u...',
                     int(prefix, 2), len(prefix))
        self._abortTunnelKiller(prefix)
        connection = self._connection_dict.pop(prefix)
        self.freeInterface(connection.iface)
        connection.close()
        if self._gateway_manager is not None:
            for ip in connection:
                self._gateway_manager.remove(ip)
        logging.trace('Connection with %u/%u killed',
                      int(prefix, 2), len(prefix))

    def _newTunnelScore(self, prefix):
        return (prefix in self._neighbour_set) + random.random()

    def _makeTunnel(self, prefix, address):
        if prefix in self._served or prefix in self._connection_dict:
            return False
        assert prefix != self._prefix, self.__dict__
        address_list = []
        same_country  = self.cache.same_country
        for x in utils.parse_address(address):
            if x[2] in self._disable_proto:
                continue
            if same_country:
                family, ip = resolve(*x[:3])
                my_country = self._country.get(family, self._conf_country)
                if my_country:
                    for ip in ip:
                        # Use geoip if there is no country in the address
                        country = x[3] if len(x) > 3 else self._geoiplookup(ip)
                        if country and (country != my_country
                                        if my_country in same_country else
                                        country in same_country):
                            logging.debug('Do not tunnel to %s (%s -> %s)',
                                          ip, my_country, country)
                        else:
                            address_list.append((ip, x[1], x[2]))
                    continue
            address_list.append(x[:3])
        self.cache.connecting(prefix, True)
        if not address_list:
            return False
        logging.info('Establishing a connection with %u/%u',
                     int(prefix, 2), len(prefix))
        with utils.exit:
            iface = self._getFreeInterface(prefix)
            self._connection_dict[prefix] = c = Connection(
                self, address_list, iface, prefix)
        if self._gateway_manager is not None:
            for ip in c:
                self._gateway_manager.add(ip, True)
        c.open()
        return True

    def _makeNewTunnels(self, route_dumped):
        count = self._client_count - len(self._connection_dict)
        logging.debug('_makeNewTunnels(route_dumped=%s,count=%s)',
                      route_dumped, count)
        if not count:
            return
        # CAVEAT: Forget any peer that didn't reply to our previous address
        #         request, either because latency is too high or some packet
        #         was lost. However, this means that some time should pass
        #         before calling _makeNewTunnels again.
        self._connecting.clear()
        distant_peers = self._distant_peers
        if route_dumped:
            neighbours = self.routing.neighbours
            # Collect all nodes known by Babel
            peers = {prefix
                for neigh_routes in neighbours.values()
                for prefix in neigh_routes[1]
                if prefix}
            # Keep only distant peers.
            distant_peers[:] = peers.difference(neighbours)
            distant_peers.sort(key=self._newTunnelScore)
            # Check whether we're connected to the network.
            registry = self.cache.registry_prefix
            if registry == self._prefix:
                if not distant_peers:
                    # Faster recovery of registry node: use cache instead
                    # of waiting that another node tries to connect to it.
                    distant_peers = None
            elif (registry in peers or
                  registry in self._connection_dict or
                  registry in self._served):
                self._disconnected = 0
                # Be ready to receive any message from the registry.
                self.sendto(registry, None)
            # Do not bootstrap too often, especially if we are several
            # nodes to try.
            elif self._disconnected < time.time():
                logging.info("No route to registry (%u peers, %u distant)",
                             len(peers), len(distant_peers))
                self._disconnected = time.time() + self.timeout * (
                    1 + random.randint(0, len(peers)))
                distant_peers = None
                if peers:
                    # We aren't the only disconnected node
                    # so force rebootstrapping.
                    peer = self.cache.getBootstrapPeer()
                    if not peer:
                        # Registry dead ? Assume we're connected after all.
                        distant_peers = self._distant_peers
                    elif peer[0] not in peers:
                        # Got a node that will probably help us rejoining
                        # the network, so connect to it.
                        count -= self._makeTunnel(*peer)
                        if not count:
                            return
        elif len(distant_peers) < count or 0 < self._disconnected < time.time():
            return True
        if distant_peers:
            if count and not self._served:
                # Limit number of client tunnels if server is not reachable
                # from outside.
                count = max(0, min(2, self._client_count)
                               - len(self._connection_dict))
            # Normal operation. Choose peers to connect to by looking at the
            # routing table.
            while count and distant_peers:
                peer = distant_peers.pop()
                address = self.cache.getAddress(peer)
                if address:
                    count -= self._makeTunnel(peer, address)
                elif self.sendto(peer, b'\1'):
                    self._connecting.add(peer)
                    count -= 1
        elif distant_peers is None:
            # No route/tunnel to registry, which usually happens when starting
            # up. Select peers from cache for which we have no route.
            new = 0
            bootstrap = True
            for peer, address in self.cache.getPeerList():
                if peer not in peers:
                    bootstrap = False
                    if self._makeTunnel(peer, address):
                        new += 1
                        if new == count:
                            return
            # The following condition on 'peers' is the same as above,
            # when we asked the registry for a node to bootstrap.
            if not (new or peers):
                if bootstrap and registry != self._prefix:
                    # Startup without any good address in the cache.
                    peer = self.cache.getBootstrapPeer()
                    if peer and self._makeTunnel(*peer):
                        return
                # Failed to bootstrap ! Last chance to connect is to
                # retry an address that already failed :(
                for peer in self.cache.getPeerList(1):
                    if self._makeTunnel(*peer):
                        break

    def killAll(self):
        for prefix in list(self._connection_dict):
            self._kill(prefix)

    def handleClientEvent(self):
        msg = self._read_sock.recv(65536)
        logging.debug("handleClientEvent(%s)", msg)
        common_name, time, serial, ip = eval(msg)
        prefix = utils.binFromSubnet(common_name)
        c = self._connection_dict.get(prefix)
        if c and c.time < float(time):
            try:
                c.connected(serial)
            except (KeyError, TypeError) as e:
                logging.error("%s (route_up %s)", e, common_name)
        else:
            logging.info("ignore route_up notification for %s %r",
                         common_name, tuple(self._connection_dict))
        if self._ip_changed:
            family, address = self._ip_changed(ip)
            if address:
                if self.cache.same_country:
                    address = self._updateCountry(address)
                self._address[family] = utils.dump_address(address)
                self.cache.my_address = ';'.join(self._address.values())

    def broadcastNewVersion(self):
        self._babel_dump_new_version()
        for prefix, c in list(self._connection_dict.items()):
            if c.serial in self.cache.crl:
                self._kill(prefix)
