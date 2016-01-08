from zope.interface import Attribute, Interface
from base_tunnel_manager import IBaseTunnelManager

class ITunnelManager(IBaseTunnelManager):
    """TunnelManager interface specification

    Manager for all the tunnels used or in use by the service. When this
    interface is implemented, it means that the node can act as a client
    as well as a server.

    When this TunnelManager opens a tunnel or a connection to a remote node, it
    is considered as a client. When this TunnelManager accepts a distant node to
    connect to itself, it is considered a server.

    It also has the duty to create and delete tunnels to neighbours, and manage
    the physical layer (interfaces, ...)

    TODO: a TunnelManager just creating mapping between Connections (related to
    a neighbour) and Tunnels (physical mean of communication) ?
    """

    def handleClientEvent():
        """
        Handler for the communication with the process used as the client-side
        connection with a remote node
        """

    def resetTunnelRefresh():
        """
        Resets the timeout before the next call to refresh
        """

    def freeInterface(iface):
        """
        Mark a network interface as free (not connected to any neighbour)
        """

    def delInterfaces():
        """
        Deletes all the network interfaces created by the service
        """

    def killAll():
        """
        Closes all connections
        """

    def refresh():
        """
        Checks all tunnels status and refresh them when necessary.
        This function is to add to the callback functions list
        """

    def babel_dump():
        """
        Refreshes tunnels : kill some, abort killing some, and create new ones
        """

    def encrypt():
        """
        Returns if the tunnels should be encrypted.
        This configuration paramater is received from the registry

        Returns a boolean
        """
