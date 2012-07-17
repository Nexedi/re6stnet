import os, random, traceback
import plib, utils, db

free_interface_set = set(('client1', 'client2', 'client3', 'client4', 'client5',
                          'client6', 'client7', 'client8', 'client9', 'client10'))

class TunnelManager:

    def __init__(self, write_pipe, peers_db):
        self.write_pipe = write_pipe
        self.peers_db = peers_db
        self.connection_dict = {}

    def refresh(self):
        self.cleanDeads()
        self.removeSomeTunnels()
        self.makeNewTunnels()

    def cleanDeads(self):
        for id in self.connection_dict.keys():
            p, iface = self.connection_dict[id]
            if p.poll() != None:
                utils.log('Connection with %s has failed with return code %s' % (id, p.returncode), 3)
                free_interface_set.add(iface)
                self.peers_db.unusePeer(id)
                del self.connection_dict[id]

    def removeSomeTunnels(self):
        for i in range(0, max(0, len(self.connection_dict) - utils.config.client_count + utils.config.refresh_count)):
            peer_id = random.choice(self.connection_dict.keys())
            kill(peer_id)

    def kill(self, peer_id):
        utils.log('Killing the connection with id ' + str(peer_id), 2)
        p, iface = self.connection_dict.pop(peer_id)
        p.kill()
        free_interface_set.add(iface)
        self.peers_db.unusePeer(peer_id)

    def makeNewTunnels(self):
        try:
            for peer_id, ip, port, proto in self.peers_db.getUnusedPeers(utils.config.client_count - len(self.connection_dict), self.write_pipe):
                utils.log('Establishing a connection with id %s (%s:%s)' % (peer_id, ip, port), 2)
                iface = free_interface_set.pop()
                self.connection_dict[peer_id] = ( plib.client( ip, write_pipe, '--dev', iface, '--proto', proto, '--rport', str(port),
                    stdout=os.open(os.path.join(utils.config.log, 'vifibnet.client.%s.log' % (peer_id,)),
                                   os.O_WRONLY|os.O_CREAT|os.O_TRUNC) ), iface)
                self.peers_db.usePeer(peer_id)
        except KeyError:
            utils.log("Can't establish connection with %s : no available interface" % ip, 2)
        except Exception:
            traceback.print_exc()
