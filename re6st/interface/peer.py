from zope.interface import Attribute, Interface

class IPeer(Interface):
    """Peer interface specification

    IPeer allows the implementation of a protocol to let 2 nodes communicating
    together. It includes the primary handshake previous to any exchange, and
    the management of a session
    """

    prefix = Attribute("prefix of the distant node to which it is connected")

    def newSession(key):
        """
        Initializes the class when a new session exchange starts
        """

    def connected():
        """
        Returns a boolean indicating if a communication has already been set up
        with the distant peeer, and is still opened
        """

    def hello0(cert):
        """
        Forges a hello0 message
        """

    def hello(cert):
        """
        Forges a hello message
        """

    def hello0Sent():
        """
        Marks than a hello0 message has been sent
        """

    def sent():
        """
        Acknowledges the instance that a message has been sent
        """

    def encode(msg, pack):
        """
        Encapsulates a message to be sent

        msg -- message to send
        pack -- structure format of header
        """

    def decode(msg, unpack):
        """
        Decapsulates data from a network message

        msg -- message
        unpack -- unpacking structure format of message header
        """
