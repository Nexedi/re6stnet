import socket
import uuid
import log

# create an upd socket
# listen on it for incoming messages and forward them
# manage the forwarding routing table
# the peudo-code can be found here http://en.wikipedia.org/wiki/Chord_%28peer-to-peer%29

class RingMember:

    def __init__(self, id, ip, port):
        self.port = port
        self.ip = ip
        self.id = id

    def toString(self):
        return str(self.id) + ' ' + self.ip + ' ' + str(self.port)

class Ring:
    
    def __init__(self, entryPoint):
        # initialize the connection
        self.sock = socket.socket( socket.AF_INET6, socket.SOCK_DGRAM )
        self.sock.bind(('', 0))
        self.me = RingMember(uuid.uuid1().int ,'',  self.sock.getsockname()[1]) # TODO : get the address
        # to enter the ring
        self.predecessor = None
        if entryPoint == None:
            self.successor = self.me
        else:
            self.send('FIND_SUCCESSOR ' + str(self.me.id) + ' ' + self.me.toString(), entrypoint)
        log.log('Init the ring with me = ' + self.me.toString(), 3)

    # TODO :
    def handleMessages(self):
        # TODO : switch to log
        log.log('Handling messages ...', 3)
        pass

    def send(self, message, target):
        # TODO : switch to log
        log.log('Sending : ' + message + ' to ' + target.toString(), 5)
        self.sock.sendTo(message, (target.ip, target.port))

    def findSuccessor(self, id, sender):
        if self.id < id and id <= self.successor:
            self.send('SUCCESSOR_IS ' + self.successor.toString(), sender)
        else:
            self.send('FIND_SUCCESSOR ' + str(id) + ' ' + sender.toString(), successor) # TODO : use the fingers

# Just copying the pseudocode from wikipedia, I will make it work later
# Possible messages (just for the creation of the ring) :
#
# find_successor $id $sender : $sender whants the IP of the successor of $id
# successor_is $ip $successor
# get_predecessor
# notify $sender_ip $sender_id
# PING

    # called periodically
    # pb : how to fix successor
#    def stabilize(self):
#        x = SEND get_predecessor TO self.successor
#        if n < x && x < self.successor:
#            self.successor = x
#            SEND notify self.ip, self.id TO self.successor
    
#    def notify(self, n2)
#        if self.predecessor == None || (predecessor < n2 && n2 < n):
#            self.predecessor = n2

    # to be called periodically
#    def fixFingers(self)
#        next = (next + 1) mod (nFingers) # Or Random, cf google
#        finger[next] = find_successor(n+2^{next-1});
    
    # to be called periodically
#    def checkPredecessor(self)
#        if NO PING from self.predecessor:
#            self.predecessor = None
