from zope.interface import Interface

class IRoutingProtocol(Interface):
    """Routing Protocol interface specification

    The under-layer routing protocol in use in re6st should be able
    to respond to these requests
    """

    def reset():
        """
        Resets the routing protocol service
        """

    def request_dump():
        """
        Requests a dump from the routing protocol
        """

    def handle_dump():
        """
        Handler for the reponse to the dump request
        """

    def send(packet):
        """
        Sends a packet via the routing protocol
        """

    def select(r, w, t):
        """
        Similar to the select system call

        r -- list of files to wait until ready for reading
        w -- list of files to wait until ready for writing
        t -- timeout list
        """

