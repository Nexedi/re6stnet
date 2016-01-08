import zope.interface

class IRegistryBackend(zope.interface.Interface):
    """RegistryBackend interface specification

    Represents the registry intelligence, which is in charge of managing the network.
    Its main tasks are : registering nodes, attributing them IP(s), revoking
    nodes, and keeping the network updated and consistent.
    """

    network_config = zope.interface.Attribute( \
      "dictionary containing the network configuration")

    def getConfig(name, *default):
        """
        Returns value of config parameter

        name -- name of the parameter whose value we want
        default -- value to return in case of failure
        """

    def setConfig(name_value):
        """
        Creates or updates parameter in config

        name_value -- tuple containing the parameter and its value
        """

    def updateNetworkConfig(_it0=None):
        """
        Updates network_config when registry configuration has changed
        """

    def encodeVersion(version):
        """
        Encodes the version, and returns it.
        The returned value should always be greater than the old one

        version -- version number
        """

    def decodeVersion(version):
        """
        Reads the version from its encoded format.

        version -- version number
        """

    def request_dump():
        """
        Requests the routing protocol to make a dump.
        This function locks the process until the dump is completed,
        or it failed, or time-out is reached
        """

    def babel_dump():
        """
        Releases the lock protecting the routing dump request
        """

    def getCert(client_prefix):
        """
        Returns certificate of a node

        client_prefix -- prefix of the node
        """

    def newPrefix(prefix_len):
        """
        Returns a free prefix

        prefix_len -- lenghth of the prefix
        """

    def getSubjectSerial(self):
        """
        Returns smallest unused serial
        """

    def createCertificate(client_prefix, subject, pubkey, not_after=None):
        """
        Creates a certificate for a new node

        client_prefix -- prefix of the node 
        subject -- subject of the certificate (= network id)
        pubkey -- public key of registry
        """

