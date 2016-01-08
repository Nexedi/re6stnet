from zope.interface import Attribute, Interface

class IBaseTunnelManager(Interface):
    """BaseTunnelManager interface specification

    Basic Tunnel Manager running a limited set of the re6st network functions.
    A BaseTunnelManager will only spawn a re6st process, used to communicate
    with other nodes of their network by opening tunnels. It won't accept
    requests of other nodes to open a tunnel and act as a server.

    The tunnel manager keeps a list of callback functions to run at a given date
    """

    def select(r, w, t):
        """
        Similar to the select system call

        r -- list of files to wait until ready for reading
        w -- list of files to wait until ready for writing
        t -- timeout list
        """

    def selectTimeout(next, callback, force=None):
        """
        Updates the next date on which the callback function has to be run, if
        it is sooner that the previous defined date

        next -- date when to run the callback function. If None, deletes the 
                callback from the list of callbacks
        callback -- function to call on timeout
        """

    def newVersion():
        """
        Apply new network parameters when new ones have been received from
        the registry.
        Here is a good place to clean revocated nodes
        """

    def invalidatePeers():
        """
        Removes known peers whose certificates have expired
        """

    def handleServerEvent(sock):
        """
        Handler for the communication with the process used as the server-side
        connection with a remote node

        sock -- socket to read from
        """

    def handlePeerEvent():
        """
        Handler for the messages received by peers wanting to communicate
        directly with the re6st process of this node.
        This function has to be appended in the watch-list for reading by the
        select event
        """

    def sendto(prefix, msg):
        """
        Sends a message to a re6st node, using IPv6.
        The destination port is the one on which re6st is listening.
        Typically, messages sent with this function will be handle by
        the distant "handlePeerEvent" function

        prefix -- prefix of peer
        msg -- message to send
        """

