import os, random, traceback, time, struct, subprocess, operator, math
import plib, utils, db

log = None
smooth = 0.3     # this is used to smooth the traffic sampling. Lower value
                 # mean more smooth
protected = 0.2  # ratio of the tunnels protected against kill because they are
                 # used a lot

# Be carfull the refresh interval should let the routes be established


class Connection:

    def __init__(self, address, write_pipe, hello, iface, prefix,
            ovpn_args):
        self.process = plib.client(address, write_pipe, hello, '--dev', iface,
                *ovpn_args, stdout=os.open(os.path.join(log,
                'vifibnet.client.%s.log' % (prefix,)),
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC),
                stderr=subprocess.STDOUT)

        self.iface = iface
        self.routes = 0
        self._prefix = prefix
        self.bandwidth = None
        self._last_trafic = None

    # TODO : update the stats
    def refresh(self):
        # Check that the connection is alive
        if self.process.poll() != None:
            utils.log('Connection with %s has failed with return code %s'
                     % (self._prefix, self.process.returncode), 3)
            return False

        # self._updateBandwidth()
        return True

    # Unused for now. By killing tunnels with significantly lower trafic
    # in comparison to other tunnels, we hope to connect to nodes with
    # better bandwith, in order to improve connectivity with destinations
    # we are really interested in.
    def _updateBandwidth(self):
        try:
            f_rx = open('/sys/class/net/%s/statistics/rx_bytes' %
                    self.iface, 'r')
            f_tx = open('/sys/class/net/%s/statistics/tx_bytes' %
                    self.iface, 'r')

            trafic = int(f_rx.read()) + int(f_tx.read())
            t = time.time()

            if bool(self._last_trafic):
                bw = (trafic - self._last_trafic) / (t -
                        self._last_trafic_update)
                if bool(self.bandwidth):
                    self.bandwidth = ((1 - smooth) * self.bandwidth
                            + smooth * bw)
                else:
                    self.bandwidth = bw

                utils.log('New bandwidth calculated on iface %s : %s' %
                        (self.iface, self.bandwidth), 4)

            self._last_trafic_update = t
            self._last_trafic = trafic
        except IOError:  # This just means that the interface is downs
            utils.log('Unable to calculate bandwidth on iface %s' %
                self.iface, 4)


class TunnelManager:

    def __init__(self, write_pipe, peer_db, openvpn_args, hello_interval,
                refresh, connection_count, refresh_rate, iface_list, network):
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
        self.free_interface_set = set(('client1', 'client2', 'client3',
                                       'client4', 'client5', 'client6',
                                       'client7', 'client8', 'client9',
                                       'client10', 'client11', 'client12'))
        self.next_refresh = time.time()

        self._client_count = int(math.ceil(float(connection_count) / 2.0))
        self._refresh_count = int(math.ceil(refresh_rate * self._client_count))

    def refresh(self):
        utils.log('Refreshing the tunnels...', 2)
        self._cleanDeads()
        self._countRoutes()
        self._removeSomeTunnels()
        self._makeNewTunnels()
        utils.log('Tunnels refreshed', 2)
        self.next_refresh = time.time() + self._refresh_time

    def _cleanDeads(self):
        for prefix in self._connection_dict.keys():
            if not self._connection_dict[prefix].refresh():
                self._kill(prefix)
                self._peer_db.flagPeer(prefix)

    def _removeSomeTunnels(self):
        # Get the candidates to killing
        candidates = sorted(self._connection_dict, key=lambda p:
                self._connection_dict[p].bandwidth)
        candidates = sorted(candidates[0: int(math.ceil((1 - protected)
                * len(candidates)))], key=lambda p:
                self._connection_dict[p].routes)
        for prefix in candidates[0: max(0, len(self._connection_dict) -
                self._client_count + self._refresh_count)]:
            self._kill(prefix)

    def _kill(self, prefix):
        utils.log('Killing the connection with %s...' % (prefix,), 2)
        connection = self._connection_dict.pop(prefix)
        try:
            connection.process.terminate()
        except OSError:
            # If the process is already exited
            pass
        self.free_interface_set.add(connection.iface)
        self._peer_db.unusePeer(prefix)
        del self._iface_to_prefix[connection.iface]
        utils.log('Connection with %s killed' % (prefix,), 2)

    def _makeNewTunnels(self):
        i = 0
        utils.log('Trying to make %i new tunnels...' %
                (self._client_count - len(self._connection_dict)), 5)
        try:
            for prefix, address in self._peer_db.getUnusedPeers(
                    self._client_count - len(self._connection_dict)):
                utils.log('Establishing a connection with %s' % prefix, 2)
                iface = self.free_interface_set.pop()
                self._connection_dict[prefix] = Connection(address,
                        self._write_pipe, self._hello, iface,
                        prefix, self._ovpn_args)
                self._iface_to_prefix[iface] = prefix
                self._peer_db.usePeer(prefix)
                i += 1
            utils.log('%u new tunnels established' % (i,), 3)
        except KeyError:
            utils.log("""Can't establish connection with %s
                    : no available interface""" % prefix, 2)
        except Exception:
            traceback.print_exc()

    def _countRoutes(self):
        utils.log('Starting to count the routes on each interface...', 3)
        self._peer_db.clear_blacklist(0)
        for iface in self._iface_to_prefix.keys():
            self._connection_dict[self._iface_to_prefix[iface]].routes = 0
        for line in open('/proc/net/ipv6_route'):
            line = line.split()
            ip = bin(int(line[0], 16))[2:].rjust(128, '0')

            if ip.startswith(self._network):
                iface = line[-1]
                subnet_size = int(line[1], 16)
                utils.log('Route on iface %s detected to %s/%s'
                        % (iface, ip, subnet_size), 8)
                if iface in self._iface_to_prefix.keys():
                    self._connection_dict[self._iface_to_prefix[iface]].routes += 1
                if iface in self._iface_list and self._net_len < subnet_size < 128:
                    prefix = ip[self._net_len:subnet_size]
                    utils.log('A route to %s has been discovered on the LAN'
                            % (prefix,), 3)
                    self._peer_db.blacklist(prefix, 0)

        utils.log("Routes have been counted", 3)
        for p in self._connection_dict.keys():
            utils.log('Routes on iface %s : %s' % (
                self._connection_dict[p].iface,
                self._connection_dict[p].routes), 5)

    def killAll(self):
        for prefix in self._connection_dict.keys():
            self._kill(prefix)
            
