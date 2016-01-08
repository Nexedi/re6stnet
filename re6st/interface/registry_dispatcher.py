import zope.interface

class IRegistryDispatcher(zope.interface.Interface):
    """RegistryDispatcher interface specification

    The registry dispatcher is the door to the network services provided by
    the registry.
    It should spawn and manage the network facilities in use to communicate
    with the nodes (answering queries, sending orders, gathering
    information, ...). When sending answers, the dispatcher could just send it
    to the closest node, which will do the routing. This node is likely to run
    on the same physical machine.
    """

    def handle_request(request, method, kw):
        """
        This function is a dispatcher of HTTP requests. It is called by
        the handler of the BaseHTTPServer spawned by the re6st service

        request -- HTTP request (BaseHTTPRequestHandler)
        method -- action requested by node. The method called should just
                  returns the body of the response, and not answer by itself
        kw -- dict containing the parameters extracted from the HTTP query
        """

    def select(r, w, t):
        """
        Similar to the select system call

        r -- list of files to wait until ready for reading
        w -- list of files to wait until ready for writing
        t -- timeout list
        """

    def sendto(prefix, code):
        """
        Send a message to a re6st node, containing a code. This is used to
        send instructions directly to the re6st process of client nodes

        prefix -- prefix of the client node
        code -- code to send
        """

    def recv(code):
        """
        Reads message from socket and returns its 
        content if the code is the one expected

        code -- code identifying the message type

        Returns : (prefix, msg) or None
                  with prefix identifying the emitter
        """

