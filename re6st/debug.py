import errno, os, socket, stat, threading


class Socket:

    def __init__(self, socket: socket.socket):
        # In case that the default timeout is not None.
        socket.settimeout(None)
        self._socket = socket
        self._buf = b''

    def close(self):
        self._socket.close()

    def write(self, data: bytes):
        self._socket.send(data)

    def readline(self) -> bytes:
        recv = self._socket.recv
        data = self._buf
        while True:
            i = 1 + data.find(b'\n')
            if i:
                self._buf = data[i:]
                return data[:i]
            d = recv(4096)
            data += d
            if not d:
                self._buf = b''
                return data

    def flush(self):
        pass

    def closed(self):
        self._socket.setblocking(0)
        try:
            self._socket.recv(0)
            return True
        except socket.error as e:
            if e.errno != errno.EAGAIN:
                raise
            self._socket.setblocking(1)
        return False


class Console:

    def __init__(self, path, pdb):
        self.path = path
        s = self._sock = socket.socket(socket.AF_UNIX,
            socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
        try:
            self._removeSocket()
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
        s.bind(path)
        s.listen(5)
        def accept():
            t = threading.Thread(target=pdb, args=(Socket(s.accept()[0]),))
            t.daemon = True
            t.start()
        def select(r, w, t):
            r[s] = accept
        self.select = select

    def close(self):
        self._removeSocket()
        self._sock.close()

    def _removeSocket(self):
        if stat.S_ISSOCK(os.lstat(self.path).st_mode):
            os.remove(self.path)
