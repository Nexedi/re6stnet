import zope.interface

class IRPCManager(zope.interface.Interface):
    """RPCRegistryServer interface specification

    Implementation to query the RPC registry server. This interface should be
    implemented both by the RPC server and the clients.
    This interface is an exhaustive list of the requests that the server should
    be able to answer to nodes. The method parameters are the arguments expected
    by the remote registry procedures.

    On the registry side, a method named "handle_request" should be provided,
    used as a dispatcher for the called methods.
    """

    def hello(client_prefix):
        """
        Starts the handshake (hello) between a node and the registry
        """

    def requestToken(email):
        """
        Generates a token and send it to the email address. This token is
        necessary to authentify the client for its first certificate request

        email -- email address to which the token will be sent
        """

    def requestCertificate(token, req):
        """
        Asks the registry for a certificate associated to the token.
        If the case of anonymous users able to register is accepted,
        the token parameter can be None

        token -- token received to the registered email address
        req -- certificate request to be validated by the CA authority
        """

    def renewCertificate(cn):
        """
        Renews the certificate of a node

        cn -- prefix of the requesting node
        """

    def getCa():
        """
        Asks the registry for the CA's certificate
        """

    def getBootstrapPeer(cn):
        """
        Returns a list of peers for bootstraping a node.
        The returned message must be encrypted with this node's certificate

        cn -- prefix of the requesting node
        """

    def getNetworkConfig(cn):
        """
        Asks the registry for the current network configuration

        cn -- prefix of the requesting node
        """
