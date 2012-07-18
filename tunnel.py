import os, random, traceback, time
import plib, utils, db

log = None

class TunnelManager:

    def __init__(self, write_pipe, peer_db, openvpn_args, refresh, connection_count, refresh_rate):
        self._write_pipe = write_pipe
        self._peer_db = peer_db
        self._connection_dict = {}
        self._ovpn_args = openvpn_args
        self._refresh_time = refresh
        self.free_interface_set = set(('client1', 'client2', 'client3', 'client4', 'client5',
                                       'client6', 'client7', 'client8', 'client9', 'client10'))
        self.next_refresh = time.time()

        # TODO : choose this automatically
        self._client_count = connection_count/2
        self._refresh_count = refresh_rate*self._client_count

    def refresh(self):
        utils.log('Refreshing the tunnels', 2)
        self._cleanDeads()
        self._removeSomeTunnels()
        self._makeNewTunnels()
        self.next_refresh = time.time() + self._refresh_time

    def _cleanDeads(self):
        for id in self._connection_dict.keys():
            p, iface = self._connection_dict[id]
            if p.poll() != None:
                utils.log('Connection with %s has failed with return code %s' % (id, p.returncode), 3)
                self.free_interface_set.add(iface)
                self._peer_db.unusePeer(id)
                del self._connection_dict[id]

    def _removeSomeTunnels(self):
        for i in range(0, max(0, len(self._connection_dict) - self._client_count + self._refresh_count)):
            peer_id = random.choice(self._connection_dict.keys())
            self._kill(peer_id)

    def _kill(self, peer_id):
        utils.log('Killing the connection with id ' + str(peer_id), 2)
        p, iface = self._connection_dict.pop(peer_id)
        p.kill()
        self.free_interface_set.add(iface)
        self._peer_db.unusePeer(peer_id)

    def _makeNewTunnels(self):
        #utils.log('Making %i new tunnels' % (self._client_count - len(self._connection_dict)), 3)
        try:
            for peer_id, ip, port, proto in self._peer_db.getUnusedPeers(self._client_count - len(self._connection_dict)):
                utils.log('Establishing a connection with id %s (%s:%s)' % (peer_id, ip, port), 2)
                iface = self.free_interface_set.pop()
                self._connection_dict[peer_id] = ( plib.client( ip, self._write_pipe,
                    '--dev', iface, '--proto', proto, '--rport', str(port), *self._ovpn_args,
                    stdout=os.open(os.path.join(log, 'vifibnet.client.%s.log' % (peer_id,)),
                                   os.O_WRONLY|os.O_CREAT|os.O_TRUNC) ), iface)
                self._peer_db.usePeer(peer_id)
        except KeyError:
            utils.log("Can't establish connection with %s : no available interface" % ip, 2)
        except Exception:
            traceback.print_exc()
