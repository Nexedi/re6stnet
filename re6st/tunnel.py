import os, traceback, time, subprocess, logging
import socket
import random
import plib
import utils

# Be carfull the refresh interval should let the routes be established


class Connection:

    def __init__(self, address, write_pipe, hello, iface, prefix, encrypt,
            ovpn_args):
        self.process = plib.client(iface, address, write_pipe, hello, encrypt,
                                   *ovpn_args)
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
                refresh, connection_count, iface_list, network, prefix, nSend,
                encrypt):
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
        self._nSend = nSend
        self._encrypt = encrypt
        self._fast_start_done = False

        self.next_refresh = time.time()
        self._next_tunnel_refresh = time.time()

        self._client_count = (connection_count + 1) // 2
        self._refresh_count = 1
        self.free_interface_set = set('re6stnet' + str(i)
            for i in xrange(1, self._client_count + 1))

    def refresh(self):
        logging.debug('Checking tunnels...')
        self._cleanDeads()
        if self._next_tunnel_refresh < time.time():
            self._countRoutes()
            self._removeSomeTunnels()
            self._next_tunnel_refresh = time.time() + self._refresh_time
        self._makeNewTunnels()
        self.next_refresh = time.time() + 5

    def _cleanDeads(self):
        for prefix in self._connection_dict.keys():
            if not self._connection_dict[prefix].refresh():
                self._kill(prefix)

    def _removeSomeTunnels(self):
        # Get the candidates to killing
        candidates = sorted(self._connection_dict, key=lambda p:
                self._connection_dict[p].routes)
        for prefix in candidates[0: max(0, len(self._connection_dict) -
                self._client_count + self._refresh_count)]:
            self._kill(prefix)

    def _kill(self, prefix, kill=False):
        logging.info('Killing the connection with %s/%u...'
                % (hex(int(prefix, 2))[2:], len(prefix)))
        connection = self._connection_dict.pop(prefix)
        try:
            getattr(connection.process, 'kill' if kill else 'terminate')()
        except OSError:
            # If the process is already exited
            pass
        self.free_interface_set.add(connection.iface)
        self._peer_db.unusePeer(prefix)
        del self._iface_to_prefix[connection.iface]
        logging.trace('Connection with %s/%u killed'
                % (hex(int(prefix, 2))[2:], len(prefix)))

    def _makeNewTunnels(self):
        tunnel_to_make = self._client_count - len(self._connection_dict)
        if tunnel_to_make <= 0:
            return
        i = 0
        logging.trace('Trying to make %i new tunnels...' % tunnel_to_make)
        try:
            for prefix, address in self._peer_db.getUnusedPeers(tunnel_to_make):
                logging.info('Establishing a connection with %s/%u' %
                        (hex(int(prefix, 2))[2:], len(prefix)))
                iface = self.free_interface_set.pop()
                self._connection_dict[prefix] = Connection(address,
                        self._write_pipe, self._hello, iface,
                        prefix, self._encrypt, self._ovpn_args)
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
        possiblePeers = set()
        for iface in self._iface_to_prefix.keys():
            self._connection_dict[self._iface_to_prefix[iface]].routes = 0
        for line in open('/proc/net/ipv6_route'):
            line = line.split()
            ip = bin(int(line[0], 16))[2:].rjust(128, '0')

            if (ip.startswith(self._network) and
                    not ip.startswith(self._network + self._prefix)):
                iface = line[-1]
                subnet_size = int(line[1], 16)
                logging.trace('Route on iface %s detected to %s/%s'
                        % (iface, line[0], subnet_size))
                if iface in self._iface_to_prefix.keys():
                    self._connection_dict[self._iface_to_prefix[iface]].routes += 1
                if iface in self._iface_list and self._net_len < subnet_size < 128:
                    prefix = ip[self._net_len:subnet_size]
                    logging.debug('A route to %s has been discovered on the LAN'
                            % hex(int(prefix, 2))[2:])
                    self._peer_db.blacklist(prefix, 0)
                possiblePeers.add(line[0])

        if not self._fast_start_done and len(possiblePeers) > 4:
            nSend = min(self._peer_db.db_size, len(possiblePeers))
        else:
            nSend = min(2, len(possiblePeers))
        for ip in random.sample(possiblePeers, nSend):
            self._notifyPeer(ip)

        logging.debug("Routes have been counted")
        for p in self._connection_dict.keys():
            logging.trace('Routes on iface %s : %s' % (
                self._connection_dict[p].iface,
                self._connection_dict[p].routes))

    def killAll(self):
        for prefix in self._connection_dict.keys():
            self._kill(prefix, True)

    def checkIncomingTunnel(self, prefix):
        if prefix in self._connection_dict:
            if prefix < self._prefix:
                return False
            else:
                self._kill(prefix)
        return True

    def _notifyPeer(self, peerIp):
        try:
            if self._peer_db.address:
                ip = '%s:%s:%s:%s:%s:%s:%s:%s' % (peerIp[0:4], peerIp[4:8], peerIp[8:12],
                    peerIp[12:16], peerIp[16:20], peerIp[20:24], peerIp[24:28], peerIp[28:32])
                logging.trace('Notifying peer %s' % ip)
                self._peer_db.sock.sendto('%s %s\n' % (self._prefix, utils.address_str(self._peer_db.address)), (ip, 326))
        except socket.error, e:
            logging.debug('Unable to notify %s' % ip)
            logging.debug('socket.error : %s' % e)
