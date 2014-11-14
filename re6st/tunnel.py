import logging, os, random, socket, subprocess, time, weakref
from collections import defaultdict, deque
from . import ctl, plib, utils, version

PORT = 326

# Be careful the refresh interval should let the routes be established


class MultiGatewayManager(dict):

    def __init__(self, gateway):
        self._gw = gateway

    def _route(self, cmd, dest, gw):
        if gw:
            cmd = 'ip', '-4', 'route', cmd, '%s/32' % dest, 'via', gw
            logging.trace('%r', cmd)
            subprocess.check_call(cmd)

    def add(self, dest, route):
        try:
            self[dest][1] += 1
        except KeyError:
            gw = self._gw(dest) if route else None
            self[dest] = [gw, 0]
            self._route('add', dest, gw)

    def remove(self, dest):
        gw, count = self[dest]
        if count:
            self[dest][1] = count - 1
        else:
            del self[dest]
            try:
                self._route('del', dest, gw)
            except:
                pass

class Connection(object):

    _retry = 0
    time = float('inf')

    def __init__(self, tunnel_manager, address_list, iface, prefix):
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
            '--tls-remote', '%u/%u' % (int(self._prefix, 2), len(self._prefix)),
            '--resolv-retry', '0',
            '--connect-retry-max', '3', '--tls-exit',
            '--remap-usr1', 'SIGTERM',
            '--ping-exit', str(tm.timeout),
            '--route-up', '%s %u' % (plib.ovpn_client, tm.write_pipe),
            *tm.ovpn_args)
        tm.resetTunnelRefresh()
        self._retry += 1

    def connected(self):
        i = self._retry - 1
        self._retry = None
        db = self.tunnel_manager.peer_db
        if i:
            db.addPeer(self._prefix, ','.join(self.address_list[i]), True)
        else:
            db.connecting(self._prefix, 0)

    def close(self):
        try:
            self.process.stop()
        except (AttributeError, OSError):
            pass # we already polled an exited process

    def refresh(self):
        # Check that the connection is alive
        if self.process.poll() != None:
            logging.info('Connection with %s has failed with return code %s',
                         self._prefix, self.process.returncode)
            if self._retry is None or len(self.address_list) <= self._retry:
                return False
            logging.info('Retrying with alternate address')
            self.close()
            self.open()
        return True

class TunnelKiller(object):

    state = None

    def __init__(self, peer, tunnel_manager, client=False):
        self.peer = peer
        self.tm = weakref.proxy(tunnel_manager)
        self.timeout = time.time() + 2 * tunnel_manager.timeout
        self.client = client
        self()

    def __call__(self):
        if self.state:
            return getattr(self, self.state)()
        tm_ctl = self.tm.ctl
        try:
            neigh = tm_ctl.neighbours[self.peer][0]
        except KeyError:
            return
        self.state = 'softLocking'
        tm_ctl.send(ctl.SetCostMultiplier(neigh.address, neigh.ifindex, 4096))
        self.address = neigh.address
        self.ifindex = neigh.ifindex
        self.cost_multiplier = neigh.cost_multiplier

    def softLocking(self):
        tm = self.tm
        if self.peer in tm.ctl.neighbours or None in tm.ctl.neighbours:
            return
        tm.ctl.send(ctl.SetCostMultiplier(self.address, self.ifindex, 0))
        self.state = "hardLocking"

    def hardLocking(self):
        tm = self.tm
        if (self.address, self.ifindex) in tm.ctl.locked:
            self.state = 'locked'
            self.timeout = time.time() + 2 * tm.timeout
            tm.sendto(self.peer, ('\4' if self.client else '\5') + tm._prefix)
        else:
            self.timeout = 0

    def unlock(self):
        if self.state:
            self.tm.ctl.send(ctl.SetCostMultiplier(self.address, self.ifindex,
                                                   self.cost_multiplier))

    def abort(self):
        if self.state != 'unlocking':
            self.state = 'unlocking'
            self.timeout = time.time() + 2 * self.tm.timeout

    locked = unlocking = lambda _: None


class TunnelManager(object):

    def __init__(self, control_socket, peer_db, openvpn_args, timeout,
                refresh, client_count, iface_list, network, prefix,
                address, ip_changed, encrypt, remote_gateway, disable_proto,
                neighbour_list=()):
        self.ctl = ctl.Babel(control_socket, weakref.proxy(self), network)
        self.encrypt = encrypt
        self.ovpn_args = openvpn_args
        self.peer_db = peer_db
        self.timeout = timeout
        # Create and open read_only pipe to get server events
        r, self.write_pipe = os.pipe()
        self._read_pipe = os.fdopen(r)
        self._connecting = set()
        self._connection_dict = {}
        self._disconnected = 0
        self._distant_peers = []
        self._iface_to_prefix = {}
        self._refresh_time = refresh
        self._network = network
        self._iface_list = iface_list
        self._prefix = prefix
        address_dict = defaultdict(list)
        for family, address in address:
            address_dict[family] += address
        self._address = dict((family, utils.dump_address(address))
                             for family, address in address_dict.iteritems()
                             if address)
        self._ip_changed = ip_changed
        self._gateway_manager = MultiGatewayManager(remote_gateway) \
                                if remote_gateway else None
        self._disable_proto = disable_proto
        self._neighbour_set = set(map(utils.binFromSubnet, neighbour_list))
        self._served = set()
        self._killing = {}

        self.sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        # See also http://stackoverflow.com/questions/597225/
        # about binding and anycast.
        self.sock.bind(('::', PORT))

        self._next_refresh = time.time()
        self.resetTunnelRefresh()

        self._client_count = client_count
        self.new_iface_list = deque('re6stnet' + str(i)
            for i in xrange(1, self._client_count + 1))
        self._free_iface_list = []

    def resetTunnelRefresh(self):
        self._next_tunnel_refresh = time.time() + self._refresh_time

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
        r[self._read_pipe] = self.handleTunnelEvent
        r[self.sock] = self.handlePeerEvent
        if self._next_refresh:
            t.append((self._next_refresh, self.refresh))
        self.ctl.select(r, w, t)

    def refresh(self):
        logging.debug('Checking tunnels...')
        self._cleanDeads()
        if self._next_tunnel_refresh < time.time() or \
           self._killing or \
           self._makeNewTunnels(False):
            self._next_refresh = None
            self.ctl.request_dump() # calls babel_dump immediately at startup
        else:
            self._next_refresh = time.time() + 5

    def babel_dump(self):
        t = time.time()
        if self._killing:
            for prefix, tunnel_killer in self._killing.items():
                if tunnel_killer.timeout < t:
                    tunnel_killer.unlock()
                    del self._killing[prefix]
                else:
                    tunnel_killer()
        remove = self._next_tunnel_refresh < t
        if remove:
            self._removeSomeTunnels()
            self.resetTunnelRefresh()
            self.peer_db.log()
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
        for prefix in self._connection_dict.keys():
            if not self._connection_dict[prefix].refresh():
                self._kill(prefix)

    def _tunnelScore(self, prefix):
        n = 0
        try:
            for x in self.ctl.neighbours[prefix][1]:
                if x:
                    n += 1
        except KeyError:
            pass
        return (prefix in self._neighbour_set, n) if n else ()

    def _removeSomeTunnels(self):
        # Get the candidates to killing
        peer_set = set(self._connection_dict)
        peer_set.difference_update(self._killing)
        count = len(peer_set) - self._client_count + 1
        if count > 0:
            for prefix in sorted(peer_set, key=self._tunnelScore)[:count]:
                self._killing[prefix] = TunnelKiller(prefix, self, True)

    def _abortTunnelKiller(self, prefix):
        tunnel_killer = self._killing.get(prefix)
        if tunnel_killer:
            if tunnel_killer.state:
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
        address = [x for x in utils.parse_address(address)
                     if x[2] not in self._disable_proto]
        self.peer_db.connecting(prefix, 1)
        if not address:
            return False
        logging.info('Establishing a connection with %u/%u',
                     int(prefix, 2), len(prefix))
        with utils.exit:
            iface = self._getFreeInterface(prefix)
            self._connection_dict[prefix] = c = Connection(self, address, iface, prefix)
        if self._gateway_manager is not None:
            for ip in c:
                self._gateway_manager.add(ip, True)
        c.open()
        return True

    def _makeNewTunnels(self, route_dumped):
        count = self._client_count - len(self._connection_dict)
        if not count:
            return
        # CAVEAT: Forget any peer that didn't reply to our previous address
        #         request, either because latency is too high or some packet
        #         was lost. However, this means that some time should pass
        #         before calling _makeNewTunnels again.
        self._connecting.clear()
        distant_peers = self._distant_peers
        if route_dumped:
            logging.debug('Analyze routes ...')
            neighbours = self.ctl.neighbours
            # Collect all nodes known by Babel
            peers = set(prefix
                for neigh_routes in neighbours.itervalues()
                for prefix in neigh_routes[1]
                if prefix)
            # Keep only distant peers.
            distant_peers[:] = peers.difference(neighbours)
            distant_peers.sort(key=self._newTunnelScore)
            # Check whether we're connected to the network.
            registry = self.peer_db.registry_prefix
            if (registry == self._prefix or registry in peers
                                         or registry in self._connection_dict
                                         or registry in self._served):
                self._disconnected = 0
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
                    peer = self.peer_db.getBootstrapPeer()
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
            # Normal operation. Choose peers to connect to by looking at the
            # routing table.
            while count and distant_peers:
                peer = distant_peers.pop()
                address = self.peer_db.getAddress(peer)
                if address:
                    count -= self._makeTunnel(peer, address)
                elif self.sendto(peer, '\2'):
                    self._connecting.add(peer)
                    count -= 1
        elif distant_peers is None:
            # No route/tunnel to registry, which usually happens when starting
            # up. Select peers from cache for which we have no route.
            new = 0
            bootstrap = True
            for peer, address in self.peer_db.getPeerList():
                if peer not in peers:
                    bootstrap = False
                    if self._makeTunnel(peer, address):
                        new += 1
                        if new == count:
                            return
            # The following condition on 'peers' is the same as above,
            # when we asked the registry for a node to bootstrap.
            if not (new or peers):
                if bootstrap:
                    # Startup without any good address in the cache.
                    peer = self.peer_db.getBootstrapPeer()
                    if peer and self._makeTunnel(*peer):
                        return
                # Failed to bootstrap ! Last change to connect is to
                # retry an address that already failed :(
                for peer in self.peer_db.getPeerList(1):
                    if self._makeTunnel(*peer):
                        break

    def killAll(self):
        for prefix in self._connection_dict.keys():
            self._kill(prefix)

    def handleTunnelEvent(self):
        try:
            msg = self._read_pipe.readline().rstrip()
            args = msg.split()
            m = getattr(self, '_ovpn_' + args.pop(0).replace('-', '_'))
        except (AttributeError, ValueError):
            logging.warning("Unknown message received from OpenVPN: %s", msg)
        else:
            logging.debug(msg)
            m(*args)

    def _ovpn_client_connect(self, common_name, trusted_ip):
        prefix = utils.binFromSubnet(common_name)
        self._served.add(prefix)
        if self._gateway_manager is not None:
            self._gateway_manager.add(trusted_ip, False)
        if prefix in self._connection_dict and self._prefix < prefix:
            self._kill(prefix)
            self.peer_db.connecting(prefix, 0)

    def _ovpn_client_disconnect(self, common_name, trusted_ip):
        prefix = utils.binFromSubnet(common_name)
        try:
            self._served.remove(prefix)
        except KeyError:
            return
        self._abortTunnelKiller(prefix)
        if self._gateway_manager is not None:
            self._gateway_manager.remove(trusted_ip)

    def _ovpn_route_up(self, common_name, time, ip):
        prefix = utils.binFromSubnet(common_name)
        c = self._connection_dict.get(prefix)
        if c and c.time < float(time):
            try:
                c.connected()
            except (KeyError, TypeError), e:
                logging.error("%s (route_up %s)", e, common_name)
        else:
            logging.info("ignore route_up notification for %s %r",
                         common_name, tuple(self._connection_dict))
        if self._ip_changed:
            family, address = self._ip_changed(ip)
            if address:
                self._address[family] = utils.dump_address(address)

    def sendto(self, peer, msg):
        ip = utils.ipFromBin(self._network + peer)
        try:
            return self.sock.sendto(msg, (ip, PORT))
        except socket.error, e:
            logging.info('Failed to send message to %s/%s (%s)',
                         int(peer, 2), len(peer), e)

    def _sendto(self, to, msg):
        try:
            return self.sock.sendto(msg, to[:2])
        except socket.error, e:
            logging.info('Failed to send message to %s (%s)', to, e)

    def handlePeerEvent(self):
        msg, address = self.sock.recvfrom(1<<16)
        if address[0] == '::1':
            sender = None
        else:
            try:
                sender = utils.binFromIp(address[0])
            except socket.error, e:
                # inet_pton does not parse '<ipv6>%<iface>'
                logging.warning('ignored message from %r (%s)', address, e)
                return
            if not sender.startswith(self._network):
                return
        if not msg:
            return
        code = ord(msg[0])
        if code == 1: # answer
            # Old versions may send additional and obsolete addresses.
            # Ignore them, as well as truncated lines.
            try:
                prefix, address = msg[1:msg.index('\n')].split()
                int(prefix, 2)
            except ValueError:
                pass
            else:
                if prefix != self._prefix:
                    self.peer_db.addPeer(prefix, address)
                    try:
                        self._connecting.remove(prefix)
                    except KeyError:
                        pass
                    else:
                        self._makeTunnel(prefix, address)
        elif code == 2: # request
            if self._address:
                self._sendto(address, '\1%s %s\n' % (self._prefix,
                    ';'.join(self._address.itervalues())))
            #else: # I don't know my IP yet!
        elif code == 3:
            if len(msg) == 1:
                self._sendto(address, '\3' + version.version)
        elif code in (4, 5): # kill
            prefix = msg[1:]
            if sender and sender.startswith(prefix, len(self._network)):
                try:
                    tunnel_killer = self._killing[prefix]
                except KeyError:
                    if code == 4 and prefix in self._served: # request
                        self._killing[prefix] = TunnelKiller(prefix, self)
                else:
                    if code == 5 and tunnel_killer.state == 'locked': # response
                        self._kill(prefix)
        elif code == 255:
            # the registry wants to know the topology for debugging purpose
            if not sender or sender[len(self._network):].startswith(
                  self.peer_db.registry_prefix):
                msg = ['\xfe%s%u/%u\n%u\n' % (msg[1:],
                    int(self._prefix, 2), len(self._prefix),
                    len(self._connection_dict))]
                msg.extend('%u/%u\n' % (int(x, 2), len(x))
                           for x in (self._connection_dict, self._served)
                           for x in x)
                try:
                    self.sock.sendto(''.join(msg), address[:2])
                except socket.error, e:
                    pass
