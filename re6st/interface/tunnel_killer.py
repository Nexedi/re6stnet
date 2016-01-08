from zope.interface import Attribute, Interface

class ITunnelKiller(Interface):
    """Tunnel interface specification
    
    Closing a tunnel should follow this interface.
    A TunnelKiller has to be able to close connections properly, which means 
    telling the remote end-point that the tunnel should be closed, and 
    aborting the operation if the remote cannot.

    Classes implementing this interface should work like a state machine, 
    and implement these states, which should be callable :
        - softLocking : the tunnel is marked as expensive from a routing point of view.
        - hardLocking : the tunnel is marked as "canno't be used anymore"
        - locked : a request to close the tunnel has been sent to remote end-point
        - unlocking : the tunnel cannot be deleted
    """

    state = Attribute("current closing state of the tunnel")

    def softLocking():
        """
        Soft-locks the tunnel, and goes to "hardLocking" state
        """

    def hardLocking():
        """
        Hard-locks the tunnel, and goes to "locked" state
        """

    def unlocking():
        """
        Does nothing
        """

    def locked():
        """
        Does nothing
        """

    def unlock():
        """
        Resets the cost of the tunnel to its previous state
        """

    def abort():
        """
        Goes to the "unlocking" state
        """

