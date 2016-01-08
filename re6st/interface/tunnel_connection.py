from zope.interface import Attribute, Interface

class IConnection(Interface):
    """Tunnel interface specification

    Provides basic operations to manage physical tunnels
    of any kind between 2 nodes of the network
    """

    def open():
        """
        Spawns a tunnel connection to a node
        """

    def close():
        """
        Turns off the tunnel connection
        """

    def connected(serial):
        """
        Updates cache
        """

    def refresh():
        """
        Tries to restart connection if it is down
        """
