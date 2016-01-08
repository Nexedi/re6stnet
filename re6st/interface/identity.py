from zope.interface import Attribute, Interface

class IIdentity(Interface):
    """Indentity interface specification

    Each node should be authentified in order to allow secure communication.
    IIdentity sets functions which allow to verify the identity and
    the appartenance to the network of other nodes,
    and exchange with them crypted messages
    """

    prefix = Attribute("This node's prefix")

    network = Attribute("This node's network address")

    def maybeRenew(registry, crl):
        """
        Returns the next date when the membership to the network should be renewed.
        It can be because our membership expired, or CA's certificate did
        """

    def loadVerify(cert, strict=None, type=None):
        """
        OpenSSL certificate verification. Returns the string representation of
        the certificate in case of success

        cert -- certificate to verify
        strict -- returns verification result, even if certificate is correct
        type -- encoding of certificate
        """

    def verify(sign, data):
        """
        Verifies emitter's authenticity of a string

        sign -- signature of the emitter
        data -- string to verify
        """

    def sign(data):
        """
        Signs a string with the node's own certificate

        data -- string to sign
        """

    def encrypt(cert, data):
        """
        Encrypts a string to send to a node

        cert -- certificate or key used to crypt communication with this node
        data -- data to encrypt
        """

    def decrypt(data):
        """
        Deciphers data using the node's own key certificate

        data -- crypted string to read
        """

    def verifyVersion(version):
        """
        Verifies network version. Raises VerifyError if it doesn't match

        version -- version to check
        """
