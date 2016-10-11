import logging, socket, struct
from collections import namedtuple
from . import utils

uint16 = struct.Struct("!H")
header = struct.Struct("!HI")

class Struct(object):

    def __init__(self, format, *args):
        if args:
            t = namedtuple(*args)
        if isinstance(format, str):
            s = struct.Struct("!" + format)
            def encode(buffer, value):
                buffer += s.pack(*value)
            def decode(buffer, offset=0):
                return offset + s.size, t(*s.unpack_from(buffer, offset))
        else:
            def encode(buffer, value):
                for f, value in zip(format, value):
                    f.encode(buffer, value)
            def decode(buffer, offset=0):
                r = []
                for f in format:
                    offset, x = f.decode(buffer, offset)
                    r.append(x)
                return offset, t(*r)
        self.encode = encode
        self.decode = decode

class Array(object):

    def __init__(self, item):
        self._item = item

    def encode(self, buffer, value):
        buffer += uint16.pack(len(value))
        encode = self._item.encode
        for value in value:
            encode(buffer, value)

    def decode(self, buffer, offset=0):
        r = []
        o = offset + 2
        decode = self._item.decode
        for i in xrange(*uint16.unpack_from(buffer, offset)):
            o, x = decode(buffer, o)
            r.append(x)
        return o, r

class String(object):

    @staticmethod
    def encode(buffer, value):
        buffer += value + "\0"

    @staticmethod
    def decode(buffer, offset=0):
        i = buffer.index("\0", offset)
        return i + 1, buffer[offset:i]


class Buffer(object):

    def __init__(self):
        self._buf = bytearray()
        self._r = self._w = 0


    def __iadd__(self, value):
        self._buf += value
        return self

    def __len__(self):
        return len(self._buf)

    def _seek(self, r):
        n = len(self._buf)
        if r < n:
            self._r = r
        else:
            self._w -= n
            del self._buf[:]
            self._r = 0

    # reading

    @property
    def ready(self):
        return self._w <= len(self._buf)

    def want(self, n):
        self._w = self._r + n

    def unpack_from(self, struct):
        r = self._r
        value = struct.unpack_from(self._buf, r)
        self._seek(r + struct.size)
        return value

    def decode(self, decode):
        r, value = decode(self._buf, self._r)
        self._seek(r)
        return value

    try: # BBB: Python < 2.7.4 (http://bugs.python.org/issue10212)
        uint16.unpack_from(bytearray(uint16.size))
    except TypeError:
        def unpack_from(self, struct):
            r = self._r
            x = r + struct.size
            value = struct.unpack(buffer(self._buf)[r:x])
            self._seek(x)
            return value
        def decode(self, decode):
            r = self._r
            size, value = decode(buffer(self._buf)[r:])
            self._seek(r + size)
            return value

    # writing

    def send(self, socket, *args):
        r = self._r
        self._seek(r + socket.send(self._buf[r:], *args))

    def pack_into(self, struct, offset, *args):
        struct.pack_into(self._buf, offset, *args)


class Packet(object):

    response_dict = {}

    def __new__(cls, id, request, response=None):
        if response:
            cls.response_dict[id] = response.decode
        if request:
            def packet(*args):
                self = object.__new__(cls)
                self.id = id
                self.args = args
                self.request = request
                return self
            return packet

    def write(self, buffer):
        logging.trace('send %s%r', self.__class__.__name__,
                                   (self.id,) + self.args)
        offset = len(buffer)
        buffer += '\0' * header.size
        r = self.request
        if isinstance(r, Struct):
            r.encode(buffer, self.args)
        else:
            r.encode(buffer, *self.args)
        buffer.pack_into(header, offset, self.id,
                         len(buffer) - header.size - offset)


Dump = Packet(1,
  Struct("B"),
  Struct((
    Array(Struct((Struct("I", "index", "index"), String), "interface", "index name")),
    Array(Struct("16sIHHHHHiHH", "neighbour", "address ifindex reach rxcost txcost rtt rttcost channel if_up cost_multiplier")),
    Array(Struct("16sBH", "xroute", "prefix plen metric")),
    Array(Struct("16sBHHH8siiI16s16sB", "route", "prefix plen metric smoothed_metric refmetric id seqno age ifindex neigh_address nexthop flags")),
    ), "dump", "interfaces neighbours xroutes routes"))

SetCostMultiplier = Packet(2,
  Struct("16sIH"),
  Struct("B", "set_cost_multiplier", "flags"))


class BabelException(Exception): pass


class ConnectionClosed(BabelException):

    def __str__(self):
        return "connection to babeld closed (%s)" % self.args


class Babel(object):

    _decode = None

    def __init__(self, socket_path, handler, network):
        self.socket_path = socket_path
        self.handler = handler
        self.network = network
        self.locked = set()
        self.reset()

    def reset(self):
        try:
            del self.socket, self.request_dump
        except AttributeError:
            pass
        self.write_buffer = Buffer()
        self.read_buffer = Buffer()
        self.read_buffer.want(header.size)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        def select(*args):
            try:
                s.connect(self.socket_path)
            except socket.error, e:
                logging.debug("Can't connect to %r (%r)", self.socket_path, e)
                return e
            s.send("\1")
            s.setblocking(0)
            del self.select
            self.socket = s
            return self.select(*args)
        self.select = select

    def request_dump(self):
        if self.select({}, {}, ()):
            self.handle_dump((), (), (), ())
        else:
            # interfaces + neighbours + installed routes
            self.request_dump = lambda: self.send(Dump(11))
            self.request_dump()

    def send(self, packet):
        packet.write(self.write_buffer)

    def select(self, r, w, t):
        s = self.socket
        r[s] = self._read
        if self.write_buffer:
            w[s] = self._write

    def _read(self):
        d = self.socket.recv(65536)
        if not d:
            raise ConnectionClosed(self.socket_path)
        b = self.read_buffer
        b += d
        while b.ready:
            if self._decode:
                packet = b.decode(self._decode)
                self._decode = None
                b.want(header.size)
                name = packet.__class__.__name__
                logging.trace('recv %r', packet)
                try:
                    h = getattr(self, "handle_" + name)
                except AttributeError:
                    h = getattr(self.handler, "babel_" + name)
                h(*packet)
            else:
                packet_type, size = b.unpack_from(header)
                self._decode = Packet.response_dict[packet_type]
                b.want(size)

    def _write(self):
        self.write_buffer.send(self.socket)

    def handle_dump(self, interfaces, neighbours, xroutes, routes):
        # neighbours = {neigh_prefix: (neighbour, {dst_prefix: route})}
        n = dict(((n.address, n.ifindex), (n, {})) for n in neighbours)
        unidentified = set(n)
        self.neighbours = neighbours = {}
        a = len(self.network)
        for route in routes:
            assert route.flags & 1, route # installed
            if route.prefix.startswith('\0\0\0\0\0\0\0\0\0\0\xff\xff'):
                continue
            assert route.neigh_address == route.nexthop, route
            address = route.neigh_address, route.ifindex
            neigh_routes = n[address]
            ip = utils.binFromRawIp(route.prefix)
            if ip[:a] == self.network:
                prefix = ip[a:route.plen]
                if prefix and not route.refmetric:
                    neighbours[prefix] = neigh_routes
                    unidentified.remove(address)
            else:
                prefix = None
            neigh_routes[1][prefix] = route
        self.locked.clear()
        if unidentified:
            routes = {}
            for address in unidentified:
                neigh, r = n[address]
                if not neigh.cost_multiplier:
                    self.locked.add(address)
                routes.update(r)
            if routes:
                neighbours[None] = None, routes
                logging.trace("Routes via unidentified neighbours. %r",
                              neighbours)
        self.interfaces = dict((i.index, name) for i, name in interfaces)
        self.handler.babel_dump()

    def handle_set_cost_multiplier(self, flags):
        pass
