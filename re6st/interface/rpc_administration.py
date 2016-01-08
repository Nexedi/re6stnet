import zope.interface

class IRPCAdministration(zope.interface.Interface):
    """RPCRegistryServer interface specification

    RPC Specifications associated to the registry server. It provides
    procedures that are in use for maintenance activities, and should be 
    protected in consequence.
    """

    def revoke(cn_or_serial):
        """
        Revokes a node's certificate.

        cn_or_serial -- prefix of the node, or its certificate's serial
        """

    def versions():
        """
        Returns a dict with nodes prefix as keys, 
        associated to their version
        """

    def topology():
        """
        Returns a graph of the network topology as a json
        """
