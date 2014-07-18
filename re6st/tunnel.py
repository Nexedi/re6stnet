import logging, random, socket, subprocess, time
from collections import defaultdict, deque
from . import plib, utils, version

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

    _retry = routes = 0

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


class TunnelManager(object):

    def __init__(self, write_pipe, peer_db, openvpn_args, timeout,
                refresh, client_count, iface_list, network, prefix,
                address, ip_changed, encrypt, remote_gateway, disable_proto,
                neighbour_list=()):
        self.encrypt = encrypt
        self.ovpn_args = openvpn_args
        self.peer_db = peer_db
        self.timeout = timeout
        self.write_pipe = write_pipe
        self._connecting = set()
        self._connection_dict = {}
        self._disconnected = None
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

        self.sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        # See also http://stackoverflow.com/questions/597225/
        # about binding and anycast.
        self.sock.bind(('::', PORT))

        self.next_refresh = time.time()
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

    def refresh(self):
        logging.debug('Checking tunnels...')
        self._cleanDeads()
        remove = self._next_tunnel_refresh < time.time()
        if remove:
            self._countRoutes()
            self._removeSomeTunnels()
            self.resetTunnelRefresh()
            self.peer_db.log()
        self._makeNewTunnels(remove)
        # XXX: Commented code is an attempt to clean up unused interfaces but
        #      it is too aggressive. Sometimes _makeNewTunnels only asks address
        #      (and the tunnel is created when we have an answer), so when the
        #      maximum number of tunnels is reached, taps are recreated all the
        #      time.
        #      Also, babeld does not leave ipv6 membership for deleted taps,
        #      causing a memory leak in the kernel (capped by sysctl
        #      net.core.optmem_max), and after some time, new neighbours fail
        #      to see each other.
        #if remove and self._free_iface_list:
        #    self._tuntap(self._free_iface_list.pop())
        self.next_refresh = time.time() + 5

    def _cleanDeads(self):
        for prefix in self._connection_dict.keys():
            if not self._connection_dict[prefix].refresh():
                self._kill(prefix)

    def _tunnelScore(self, prefix):
        n = self._connection_dict[prefix].routes
        return (prefix in self._neighbour_set, n) if n else ()

    def _removeSomeTunnels(self):
        # Get the candidates to killing
        count = len(self._connection_dict) - self._client_count + 1
        if count > 0:
            for prefix in sorted(self._connection_dict,
                                 key=self._tunnelScore)[:count]:
                self._kill(prefix)

    def _kill(self, prefix):
        logging.info('Killing the connection with %u/%u...',
                     int(prefix, 2), len(prefix))
        connection = self._connection_dict.pop(prefix)
        self.freeInterface(connection.iface)
        connection.close()
        if self._gateway_manager is not None:
            for ip in connection:
                self._gateway_manager.remove(ip)
        logging.trace('Connection with %u/%u killed',
                      int(prefix, 2), len(prefix))

    def _makeTunnel(self, prefix, address):
        assert len(self._connection_dict) < self._client_count, (prefix, self.__dict__)
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

    def _makeNewTunnels(self, route_counted):
        count = self._client_count - len(self._connection_dict)
        if not count:
            return
        assert count >= 0
        # CAVEAT: Forget any peer that didn't reply to our previous address
        #         request, either because latency is too high or some packet
        #         was lost. However, this means that some time should pass
        #         before calling _makeNewTunnels again.
        self._connecting.clear()
        distant_peers = self._distant_peers
        if len(distant_peers) < count and not route_counted:
            self._countRoutes()
        disconnected = self._disconnected
        if disconnected is not None:
            logging.info("No route to registry (%u neighbours, %u distant"
                         " peers)", len(disconnected), len(distant_peers))
            # We aren't the registry node and we have no tunnel to or from it,
            # so it looks like we are not connected to the network, and our
            # neighbours are in the same situation.
            self._disconnected = None
            disconnected = set(disconnected).union(distant_peers)
            if disconnected:
                # We do have neighbours that are probably also disconnected,
                # so force rebootstrapping.
                peer = self.peer_db.getBootstrapPeer()
                if not peer:
                    # Registry dead ? Assume we're connected after all.
                    disconnected = None
                elif peer[0] not in disconnected:
                    # Got a node that will probably help us rejoining the
                    # network, so connect to it.
                    count -= self._makeTunnel(*peer)
        if disconnected is None:
            # Normal operation. Choose peers to connect to by looking at the
            # routing table.
            neighbour_set = self._neighbour_set.intersection(distant_peers)
            while count and distant_peers:
                if neighbour_set:
                    peer = neighbour_set.pop()
                    i = distant_peers.index(peer)
                else:
                    i = random.randrange(0, len(distant_peers))
                    peer = distant_peers[i]
                distant_peers[i] = distant_peers[-1]
                del distant_peers[-1]
                address = self.peer_db.getAddress(peer)
                if address:
                    count -= self._makeTunnel(peer, address)
                else:
                    ip = utils.ipFromBin(self._network + peer)
                    try:
                        self.sock.sendto('\2', (ip, PORT))
                    except socket.error, e:
                        logging.info('Failed to query %s (%s)', ip, e)
                    self._connecting.add(peer)
                    count -= 1
        elif count:
            # No route/tunnel to registry, which usually happens when starting
            # up. Select peers from cache for which we have no route.
            new = 0
            bootstrap = True
            for peer, address in self.peer_db.getPeerList():
                if peer not in disconnected:
                    logging.info("Try to bootstrap using peer %u/%u",
                                 int(peer, 2), len(peer))
                    bootstrap = False
                    if self._makeTunnel(peer, address):
                        new += 1
                        if new == count:
                            return
            if not (new or disconnected):
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

    def _countRoutes(self):
        logging.debug('Starting to count the routes on each interface...')
        del self._distant_peers[:]
        for conn in self._connection_dict.itervalues():
            conn.routes = 0
        other = []
        for iface, prefix in utils.iterRoutes(self._network, self._prefix):
            assert iface != 'lo', (iface, prefix)
            nexthop = self._iface_to_prefix.get(iface)
            if nexthop:
                self._connection_dict[nexthop].routes += 1
            if prefix in self._served or prefix in self._connection_dict:
                continue
            if iface in self._iface_list:
                other.append(prefix)
            else:
                self._distant_peers.append(prefix)
        registry = self.peer_db.registry_prefix
        if registry == self._prefix or any(registry in x for x in (
              self._distant_peers, other, self._served, self._connection_dict)):
            self._disconnected = None
            # XXX: When there is no new peer to connect when looking at routes
            #      coming from tunnels, we'd like to consider those discovered
            #      from the LAN. However, we don't want to create tunnels to
            #      nodes of the LAN so do nothing until we find a way to get
            #      some information from Babel.
            #if not self._distant_peers:
            #    self._distant_peers = other
        else:
            self._disconnected = other
        logging.debug("Routes counted: %u distant peers",
                      len(self._distant_peers))
        for c in self._connection_dict.itervalues():
            logging.trace('- %s: %s', c.iface, c.routes)

    def killAll(self):
        for prefix in self._connection_dict.keys():
            self._kill(prefix)

    def handleTunnelEvent(self, msg):
        try:
            msg = msg.rstrip()
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
        if self._gateway_manager is not None:
            self._gateway_manager.remove(trusted_ip)

    def _ovpn_route_up(self, common_name, ip):
        prefix = utils.binFromSubnet(common_name)
        try:
            self._connection_dict[prefix].connected()
        except KeyError:
            pass
        if self._ip_changed:
            family, address = self._ip_changed(ip)
            if address:
                self._address[family] = utils.dump_address(address)

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
          sender = utils.binFromIp(address[0])
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
            self._sendto(address, '\4' + version.version)
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
