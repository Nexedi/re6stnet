import zope.interface

class ICache(zope.interface.Interface):
    """Cache interface specification

    Saves information to faster re6st service restart.
    Also provides useful information to the re6st process when running
    """

    def connecting(prefix, connecting):
        """
        Updates number of tries to a peer

        prefix -- prefix of peer
        connecting -- number of tries of connection to this peer
        """

    def resetConnecting():
        """
        Resets cache
        """

    def addPeer(prefix, address):
        """
        Adds or updates peer in cache

        prefix -- prefix of peer to add
        address -- public address of the peer
        """

    def getAddress(prefix):
        """
        Returns public ip associated to prefix

        prefix -- prefix of a peer
        """

    def getPeerList(failed=None):
        """
        Returns all peers with their public address from cache

        failed -- value to return in case of failure
        """

    def getPeerCount(failed=None):
        """
        Returns number of peers present in the cache

        failed -- value to return in case of failure
        """

    def cacheMinimize(size):
        """
        Minimizes cache to a limited amount of tested peers

        size -- number of peers to keep
        """

    def getBootstrapPeer():
        """
        Asks a bootstrap list of peers to registry to help bootstraping
        """

    def updateConfig():
        """
        Gets new network parameters from registry
        And update config accordingly
        """

