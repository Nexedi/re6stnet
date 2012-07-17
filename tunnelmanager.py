import os, random
import openvpn
import utils
import db
from config import *

connection_dict = {} # to remember current connections we made
free_interface_set = set(('client1', 'client2', 'client3', 'client4', 'client5',
                          'client6', 'client7', 'client8', 'client9', 'client10'))

def startNewConnections(n, write_pipe):
    try:
        for peer_id, ip, port, proto in peers_db.getUnusedPeers(n):
            utils.log('Establishing a connection with id %s (%s:%s)' % (peer_id, ip, port), 2)
            iface = free_interface_set.pop()
            connection_dict[peer_id] = ( openvpn.client( ip, write_pipe, '--dev', iface, '--proto', proto, '--rport', str(port),
                stdout=os.open(os.path.join(config.log, 'vifibnet.client.%s.log' % (peer_id,)), 
                               os.O_WRONLY|os.O_CREAT|os.O_TRUNC) ),
                iface)
            peers_db.usePeer(peer_id)
    except KeyError:
        utils.log("Can't establish connection with %s : no available interface" % ip, 2)
    except Exception:
        traceback.print_exc()

def killConnection(peer_id):
    try:
        utils.log('Killing the connection with id ' + str(peer_id), 2)
        p, iface = connection_dict.pop(peer_id)
        p.kill()
        free_interface_set.add(iface)
        peers_db.unusePeer(peer_id)
    except KeyError:
        utils.log("Can't kill connection to " + peer_id + ": no existing connection", 1)
        pass
    except Exception:
        utils.log("Can't kill connection to " + peer_id + ": uncaught error", 1)
        pass

def checkConnections():
    for id in connection_dict.keys():
        p, iface = connection_dict[id]
        if p.poll() != None:
            utils.log('Connection with %s has failed with return code %s' % (id, p.returncode), 3)
            free_interface_set.add(iface)
            peers_db.unusePeer(id)
            del connection_dict[id]

def refreshConnections(write_pipe):
    checkConnections()
    # Kill some random connections
    try:
        for i in range(0, max(0, len(connection_dict) - config.client_count + config.refresh_count)):
            peer_id = random.choice(connection_dict.keys())
            killConnection(peer_id)
    except Exception:
        pass
    # Establish new connections
    startNewConnections(config.client_count - len(connection_dict), write_pipe)

