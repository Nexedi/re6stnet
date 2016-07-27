import errno, os, socket, stat, threading


class Socket(object):

    def __init__(self, socket):
        # In case that the default timeout is not None.
        socket.settimeout(None)
        self._socket = socket
        self._buf = ''

    def close(self):
        self._socket.close()

    def write(self, data):
        self._socket.send(data)

    def readline(self):
        recv = self._socket.recv
        data = self._buf
        while True:
            i = 1 + data.find('\n')
            if i:
                self._buf = data[i:]
                return data[:i]
            d = recv(4096)
            data += d
            if not d:
                self._buf = ''
                return data

    def flush(self):
        pass

    def closed(self):
        self._socket.setblocking(0)
        try:
            self._socket.recv(0)
            return True
        except socket.error, (err, _):
            if err != errno.EAGAIN:
                raise
            self._socket.setblocking(1)
        return False


class Console(object):

    def __init__(self, path, pdb):
        self.path = path
        s = socket.socket(socket.AF_UNIX)
        try:
            self.close()
        except OSError, e:
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
        if stat.S_ISSOCK(os.lstat(self.path).st_mode):
            os.remove(self.path)
