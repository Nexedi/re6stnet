import os, traceback, time, subprocess, math, logging
import plib

# Be carfull the refresh interval should let the routes be established

log = None


class Connection:

    def __init__(self, address, write_pipe, hello, iface, prefix,
            ovpn_args):
        self.process = plib.client(address, write_pipe, hello, '--dev', iface,
                *ovpn_args, stdout=os.open(os.path.join(log,
                're6stnet.client.%s.log' % (prefix,)),
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC),
                stderr=subprocess.STDOUT)

        self.iface = iface
        self.routes = 0
        self._prefix = prefix

    def refresh(self):
        # Check that the connection is alive
        if self.process.poll() != None:
            logging.info('Connection with %s has failed with return code %s'
                     % (self._prefix, self.process.returncode))
            return False
        return True


class TunnelManager:

    def __init__(self, write_pipe, peer_db, openvpn_args, hello_interval,
                refresh, connection_count, iface_list, network, prefix):
        self._write_pipe = write_pipe
        self._peer_db = peer_db
        self._connection_dict = {}
        self._iface_to_prefix = {}
        self._ovpn_args = openvpn_args
        self._hello = hello_interval
        self._refresh_time = refresh
        self._network = network
        self._net_len = len(network)
        self._iface_list = iface_list
        self._prefix = prefix

        self.next_refresh = time.time()
        self._next_tunnel_refresh = time.time()

        self._client_count = (connection_count + 1) // 2
        self._refresh_count = 1
        self.free_interface_set = set('re6stnet' + str(i)
            for i in xrange(1, self._client_count + 1))

    def refresh(self):
        logging.info('Refreshing the tunnels...')
        self._cleanDeads()
        if self._next_tunnel_refresh < time.time():
            self._countRoutes()
            self._removeSomeTunnels()
            self._next_tunnel_refresh = time.time() + self._refresh_time
        self._makeNewTunnels()
        logging.debug('Tunnels refreshed')
        self.next_refresh = time.time() + 5

    def _cleanDeads(self):
        for prefix in self._connection_dict.keys():
            if not self._connection_dict[prefix].refresh():
                self._kill(prefix)
                self._peer_db.flagPeer(prefix)

    def _removeSomeTunnels(self):
        # Get the candidates to killing
        candidates = sorted(self._connection_dict, key=lambda p:
                self._connection_dict[p].routes)
        for prefix in candidates[0: max(0, len(self._connection_dict) -
                self._client_count + self._refresh_count)]:
            self._kill(prefix)

    def _kill(self, prefix):
        logging.info('Killing the connection with %s/%u...'
                % (hex(int(prefix, 2))[2:], len(prefix)))
        connection = self._connection_dict.pop(prefix)
        try:
            connection.process.terminate()
        except OSError:
            # If the process is already exited
            pass
        self.free_interface_set.add(connection.iface)
        self._peer_db.unusePeer(prefix)
        del self._iface_to_prefix[connection.iface]
        logging.trace('Connection with %s/%u killed'
                % (hex(int(prefix, 2))[2:], len(prefix)))

    def _makeNewTunnels(self):
        i = 0
        logging.trace('Trying to make %i new tunnels...' %
                (self._client_count - len(self._connection_dict)))
        try:
            for prefix, address in self._peer_db.getUnusedPeers(
                    self._client_count - len(self._connection_dict)):
                logging.info('Establishing a connection with %s/%u' %
                        (hex(int(prefix, 2))[2:], len(prefix)))
                iface = self.free_interface_set.pop()
                self._connection_dict[prefix] = Connection(address,
                        self._write_pipe, self._hello, iface,
                        prefix, self._ovpn_args)
                self._iface_to_prefix[iface] = prefix
                self._peer_db.usePeer(prefix)
                i += 1
            logging.trace('%u new tunnels established' % (i,))
        except KeyError:
            logging.warning("""Can't establish connection with %s
                              : no available interface""" % prefix)
        except Exception:
            traceback.print_exc()

    def _countRoutes(self):
        logging.debug('Starting to count the routes on each interface...')
        self._peer_db.clear_blacklist(0)
        for iface in self._iface_to_prefix.keys():
            self._connection_dict[self._iface_to_prefix[iface]].routes = 0
        for line in open('/proc/net/ipv6_route'):
            line = line.split()
            ip = bin(int(line[0], 16))[2:].rjust(128, '0')

            if ip.startswith(self._network):
                iface = line[-1]
                subnet_size = int(line[1], 16)
                logging.trace('Route on iface %s detected to %s/%s'
                        % (iface, ip, subnet_size))
                if iface in self._iface_to_prefix.keys():
                    self._connection_dict[self._iface_to_prefix[iface]].routes += 1
                if iface in self._iface_list and self._net_len < subnet_size < 128:
                    prefix = ip[self._net_len:subnet_size]
                    logging.debug('A route to %s has been discovered on the LAN'
                            % (hex(int(prefix), 2)[2:]))
                    self._peer_db.blacklist(prefix, 0)

        logging.debug("Routes have been counted")
        for p in self._connection_dict.keys():
            logging.trace('Routes on iface %s : %s' % (
                self._connection_dict[p].iface,
                self._connection_dict[p].routes))

    def killAll(self):
        for prefix in self._connection_dict.keys():
            self._kill(prefix)

    def checkIncommingTunnel(self, prefix):
        if prefix in self._connection_dict:
            if prefix >= self._prefix:
                self._kill(prefix)
                return True
            else:
                return False
        else:
            return True
