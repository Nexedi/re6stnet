"""this program contain two function,
    RST http get,
    random drop packet of some connection
"""

from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
import logging
import queue
import random
import socket
import subprocess
import time
from threading import Event, Lock
from typing import Dict

from netfilterqueue import NetfilterQueue
import nftables
from pathlib2 import Path

from scapy.layers import http
from scapy.all import IP, TCP, UDP, Raw
from scapy.all import send


logger = logging.getLogger(__name__)
LEVEL = logging.DEBUG

QUEUE_SIZE = 100
WORKERS = 2
NFT_FILE = str(Path(__file__).parent.resolve() / "ip_rules")

Conn = namedtuple("ConnectionParameter", ["src", "sport", "dst", "dport"])


class TCPControlBlock:
    """class to track tcp connection
    GFW only detect one direction of a TCP
    """

    _renew_time = 600
    _max_traffic = 10

    def __init__(self, src, sport, dst, dport) -> None:
        self.src = src
        self.sport = sport
        self.dst = dst
        self.dport = dport
        self.ack = 0
        self.seq = 0
        # TODO: Actually, I need (src, dst, dport) to track traffic
        self.traffic = 0
        self.last_active = time.time()
        self.state = None
        self.lock = Lock()

    def update(self, packet: TCP):
        """when receive new packet, update connection info
        for simplicity, trust all incoming packet
        """
        # GFW doesn't check ack field, and ignore packet with repeat seq
        # maybe receive packet in different order, just track latest seq, ack
        # a forged packet can cheat the track system.
        with self.lock:
            if time.time() - self.last_active > self._renew_time:
                self.traffic = 0
            self.last_active = time.time()
            self.ack = max(self.ack, packet.ack)
            self.seq = max(self.seq, packet.seq + len(packet.payload))
            self.traffic += len(packet.payload)
        logger.info("traffic is %s", self.traffic)
        if self.traffic > self._max_traffic:
            self.bad_service()

    def reset_connection(self):
        """GFW seems not to distinguish which side is in China or not.
        It simply sends the same things to each side.
        """
        logger.info(
            "RST connection %s:%s -> %s:%s", self.src, self.sport, self.dst, self.dport
        )
        # to recipient
        send_rst_packet(self.src, self.dst, self.sport, self.dport, self.seq, self.ack)
        # to sender
        send_rst_packet(self.dst, self.src, self.dport, self.sport, self.ack, self.seq)

    def bad_service(self):
        """add src, dst to nft set 'bad_service', for randomly drop packet"""
        logger.info("limit connection %s -> %s", self.src, self.dst)
        nft = nftables.Nftables()
        nft.cmd("add element inet filter bad_service {%s,%s}" % (self.src, self.dst))


# class TCPConnTable(dict):
#     pass

packet_queue = queue.Queue()
tcp_table: Dict[Conn, TCPControlBlock] = {}


def accept_and_record(pkt):
    "event box, provide packet"
    logger.debug("find a packet %s", pkt)
    packet = IP(pkt.get_payload())
    if packet.proto in (socket.IPPROTO_TCP, socket.IPPROTO_UDP):
        # record only tcp, udp
        try:
            packet_queue.put(packet, block=False)
        except queue.Full:
            logger.error("recv too many packet")
    time.sleep(0.3)
    # gfw is a intrusion detect system, allow all packet
    pkt.accept()


def analysis(event: Event):
    "analysis box, consume packet"
    while not event.is_set():
        try:
            packet: IP = packet_queue.get(timeout=1)
        except queue.Empty:
            continue
        if packet.haslayer(TCP):
            logger.info("Analysis tcp %s", packet.summary())
            conn_param = Conn(packet.src, packet.sport, packet.dst, packet.dport)
            tcb = tcp_table.get(conn_param, None)
            if not tcb:
                tcp_table[conn_param] = tcb = TCPControlBlock(*conn_param)
            tcb.update(packet.payload)

            # interpret the payload of tcp
            if packet.haslayer(http.HTTPRequest):
                logger.info("find a http request")
                http_p = packet.getlayer(http.HTTPRequest)
                if http_p.Method == b"GET":
                    tcb.reset_connection()

            elif packet.haslayer(http.HTTPResponse):
                logger.info("find a http response")
            else:
                # not a http packet
                pass

        if packet.haslayer(UDP):
            udp_p = packet.payload
            if udp_p.dport == 53:
                # dns query, need dns poison
                pass


def send_rst_packet(src, dst, sport, dport, seq, ack):
    """send 2 type RST, 1 RST_1, 3 RST_2
    common:
        IP: ttl random
        TCP:
            window size: random
            option: None(even context have)
    RST_1:
        IP: id = 0, FLAGS=0
        TCP: FLAGS = "R"
    RST_2
        IP: id random, FLAGS="DF"
        TCP: FLAGS = "AR"
    """
    # type 1
    i = IP(src=src, dst=dst, id=0)
    t = TCP(sport=sport, dport=dport, seq=seq, flags="R")
    send(i / t)
    # type 2
    i.id = random.randint(0, 1 << 16 - 1)
    i.flags = "DF"
    t.flags = "RA"
    t.ack = ack
    send(i / t)
    send(i / t)
    send(i / t)


def main():
    subprocess.run(["nft", "-f", NFT_FILE], check=True)
    event = Event()
    # nft = nftables.Nftables()
    with ThreadPoolExecutor(max_workers=3) as executor:
        for _ in range(WORKERS):
            executor.submit(analysis, event)
        nfqueue = NetfilterQueue()
        nfqueue.bind(1, accept_and_record)
        try:
            nfqueue.run()
        except KeyboardInterrupt:
            event.set()
            logger.debug("set event and exit program")
        nfqueue.unbind()
    subprocess.run(("nft", "flush", "ruleset"), check=True)


if __name__ == "__main__":
    logging.basicConfig(
        level=LEVEL,
        filename="gfw.log",
        filemode="w",
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%I:%M:%S",
    )
    try:
        main()
    except Exception as e:
        logger.error(e)
