import base64  # provides functions for encoding/decoding binary data to/from printable ASCII characters
import hashlib  # implements a common interface to many different secure hash and message digest algorithms


class Hash:
    """ Simple wrapper around hashlib sha256 functions. """

    def __init__(self):
        """ Initialize hash class using hashlib sha256 implementation. """

        self.m = hashlib.sha256()

    def update(self,
               w):  # string to update hash value with
        """ Update current hash value.

        Args:
            w: String to update hash value with
        """

        self.m.update(w.encode('utf-8'))

    def get_b64(self):
        """ Get base64 encoding of the current hash value digest.

        Returns:
            Base64 encoding of the hash digest.
        """

        return base64.urlsafe_b64encode(self.m.digest()).decode('utf-8')