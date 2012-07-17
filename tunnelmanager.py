import os, random, traceback
import plib, utils, db

free_interface_set = set(('client1', 'client2', 'client3', 'client4', 'client5',
                          'client6', 'client7', 'client8', 'client9', 'client10'))

class TunnelManager:

    def __init__(self, write_pipe, peers_db):
        self._write_pipe = write_pipe
        self._peers_db = peers_db
        self._connection_dict = {}

        # TODO : choose this parameters automaticaly
        self._clientCount = 15
        self._refreshCount = 3

    def refresh(self):
        self._cleanDeads()
        self._removeSomeTunnels()
        self._makeNewTunnels()

    def _cleanDeads(self):
        for id in self._connection_dict.keys():
            p, iface = self._connection_dict[id]
            if p.poll() != None:
                utils.log('Connection with %s has failed with return code %s' % (id, p.returncode), 3)
                free_interface_set.add(iface)
                self._peers_db.unusePeer(id)
                del self._connection_dict[id]

    def _removeSomeTunnels(self):
        for i in range(0, max(0, len(self._connection_dict) - self._clientCount + self._refresh_count)):
            peer_id = random.choice(self._connection_dict.keys())
            kill(peer_id)

    def _kill(self, peer_id):
        utils.log('Killing the connection with id ' + str(peer_id), 2)
        p, iface = self._connection_dict.pop(peer_id)
        p.kill()
        free_interface_set.add(iface)
        self._peers_db.unusePeer(peer_id)

    def _makeNewTunnels(self):
        try:
            for peer_id, ip, port, proto in self._peers_db.getUnusedPeers(self._client_count - len(self._connection_dict), self._write_pipe):
                utils.log('Establishing a connection with id %s (%s:%s)' % (peer_id, ip, port), 2)
                iface = free_interface_set.pop()
                self._connection_dict[peer_id] = ( openvpn.client( ip, write_pipe, '--dev', iface, '--proto', proto, '--rport', str(port),
                    stdout=os.open(os.path.join(utils.config.log, 'vifibnet.client.%s.log' % (peer_id,)), 
                                   os.O_WRONLY|os.O_CREAT|os.O_TRUNC) ),
                                   iface)
                self._peers_db.usePeer(peer_id)
        except KeyError:
            utils.log("Can't establish connection with %s : no available interface" % ip, 2)
        except Exception:
            traceback.print_exc()
