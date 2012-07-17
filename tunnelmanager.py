import os, random, traceback
import plib, utils, db



class TunnelManager:

    def __init__(self, write_pipe, peers_db, client_count, refresh_count):
        self.write_pipe = write_pipe
        self.peers_db = peers_db
        self.connection_dict = {}
        self.client_count = client_count
        self.refresh_count = refresh_count
        self.free_interface_set = set(('client1', 'client2', 'client3', 'client4', 'client5',
                                       'client6', 'client7', 'client8', 'client9', 'client10'))

    def refresh(self):
        self.cleanDeads()
        self.removeSomeTunnels()
        self.makeNewTunnels()

    def cleanDeads(self):
        for id in self.connection_dict.keys():
            p, iface = self.connection_dict[id]
            if p.poll() != None:
                utils.log('Connection with %s has failed with return code %s' % (id, p.returncode), 3)
                self.free_interface_set.add(iface)
                self.peers_db.unusePeer(id)
                del self.connection_dict[id]

    def removeSomeTunnels(self):
        for i in range(0, max(0, len(self.connection_dict) - self.client_count + self.refresh_count)):
            peer_id = random.choice(self.connection_dict.keys())
            kill(peer_id)

    def kill(self, peer_id):
        utils.log('Killing the connection with id ' + str(peer_id), 2)
        p, iface = self.connection_dict.pop(peer_id)
        p.kill()
        self.free_interface_set.add(iface)
        self.peers_db.unusePeer(peer_id)

    def makeNewTunnels(self):
        try:
            for peer_id, ip, port, proto in self.peers_db.getUnusedPeers(self.client_count - len(self.connection_dict), self.write_pipe):
                utils.log('Establishing a connection with id %s (%s:%s)' % (peer_id, ip, port), 2)
                iface = self.free_interface_set.pop()
                self.connection_dict[peer_id] = ( plib.client( ip, write_pipe, '--dev', iface, '--proto', proto, '--rport', str(port),
                    stdout=os.open(os.path.join(utils.config.log, 'vifibnet.client.%s.log' % (peer_id,)),
                                   os.O_WRONLY|os.O_CREAT|os.O_TRUNC) ), iface)
                self.peers_db.usePeer(peer_id)
        except KeyError:
            utils.log("Can't establish connection with %s : no available interface" % ip, 2)
        except Exception:
            traceback.print_exc()
            
    def handle_message(msg):
        script_type, arg = msg.split()
        if script_type == 'client-connect':
            utils.log('Incomming connection from %s' % (arg,), 3)
        elif script_type == 'client-disconnect':
            utils.log('%s has disconnected' % (arg,), 3)
        elif script_type == 'route-up':
            utils.log('External Ip : ' + arg, 3)
        else:
            utils.log('Unknow message recieved from the openvpn pipe : ' + msg, 1)
