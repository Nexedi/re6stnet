"""wrap the deploy of re6st node, ease the creation of cert
file and run of the node
"""
import json
import shutil
import sqlite3
import weakref
import ipaddress
import time
import re
import tempfile
import logging
import errno
from subprocess import PIPE, call
from pathlib2 import Path

import re6st.tests.tools as tools

WORK_DIR = Path(__file__).parent / "temp_net_test"
DH_FILE = WORK_DIR / "dh2048.pem"

RE6STNET = "re6stnet"
RE6STNET = "python -m re6st.cli.node"
RE6ST_REGISTRY = "re6st-registry"
RE6ST_REGISTRY = "python -m re6st.cli.registry"
RE6ST_CONF = "re6st-conf"
RE6ST_CONF = "python -m re6st.cli.conf"

def initial():
    """create the workplace"""
    if not WORK_DIR.exists():
        WORK_DIR.mkdir()

def ip_to_serial(ip6):
    """convert ipv6 address to serial"""
    ip6 = ipaddress.IPv6Address(u"{}".format(ip6))
    ip6 = "1{:x}".format(int(ip6)).rstrip('0')
    return int(ip6, 16)


class Re6stRegistry(object):
    """class run a re6st-registry service on a namespace"""
    registry_seq = 0

    def __init__(self, node, ip6, client_number, port=80, recreate=False):
        self.node = node
        # TODO need set once
        self.ip = node.ip
        self.ip6 = ip6
        self.client_number = client_number
        self.port = port
        self.name = self.generate_name()

        self.path = WORK_DIR / self.name
        self.ca_key = self.path / "ca.key"
        # because re6st-conf will create ca.crt so use another name
        self.ca_crt = self.path / "ca.cert"
        self.log = self.path / "registry.log"
        self.db = self.path / "registry.db"
        self.run_path = tempfile.mkdtemp()

        if recreate and self.path.exists():
            shutil.rmtree(str(self.path))

        if not self.path.exists():
            self.create_registry()

        # use hash to identify the registry
        with self.ca_key.open() as f:
            text = f.read()
            self.ident = hash(text)

        self.clean()

        self.run()
        # wait the servcice started
        p = self.node.Popen(['python', '-c', """if 1:
        import socket, time
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        while True:
            try:
                s.connect(('localhost', {}))
                break
            except socket.error:
                time.sleep(.1)
        """.format(self.port)])

        now = time.time()
        while time.time() - now < 10:
            if p.poll() != None:
                break
            time.sleep(0.1)
        else:
            logging.error("registry failed to start, %s", self.name)
            p.destroy()
            raise Exception("registry failed to start")
        logging.info("re6st service started")

    @classmethod
    def generate_name(cls):
        cls.registry_seq += 1
        return "registry_{}".format(cls.registry_seq)

    @property
    def url(self):
        return "http://{ip}/".format(ip=self.ip)

    def create_registry(self):
        self.path.mkdir()
        tools.create_ca_file(str(self.ca_key), str(self.ca_crt),
                             serial=ip_to_serial(self.ip6))

    def run(self):
        cmd =['--ca', self.ca_crt, '--key', self.ca_key, '--dh', DH_FILE,
              '--ipv4', '10.42.0.0/16', '8', '--logfile', self.log, '--db', self.db,
              '--run', self.run_path, '--hello', '4', '--mailhost', 's', '-v4',
              '--client-count', (self.client_number+1)//2, '--port', self.port]

        #convert PosixPath to str, can be remove in python3
        cmd = map(str, cmd)

        cmd = RE6ST_REGISTRY.split() + cmd

        logging.debug("run registry %s at ns: %s with cmd: %s",
                     self.name, self.node.pid, " ".join(cmd))
        self.proc = self.node.Popen(cmd, stdout=PIPE, stderr=PIPE)

    def clean(self):
        """remove the file created last time"""
        try:
            self.log.unlink()
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def __del__(self):
        try:
            logging.debug("teminate process %s", self.proc.pid)
            self.proc.destroy()
        except:
            pass


class Re6stNode(object):
    """class run a re6stnet service on a namespace"""
    node_seq = 0

    def __init__(self, node, registry, name=None, recreate=False):
        """
        node: nemu node
        name: name for res6st node
        """
        self.name = name if name else self.generate_name()
        self.node = node
        self.registry = weakref.proxy(registry)

        self.path = WORK_DIR / self.name
        self.email = self.name + "@example.com"

        if self.name == self.registry.name:
            self.run_path = self.registry.run_path
        else:
            self.run_path = tempfile.mkdtemp()

        self.log = self.path  / "re6stnet.log"
        self.crt = self.path / "cert.crt"
        self.key = self.path / 'cert.key'
        self.console = self.run_path + "/console.sock"
        self.data_file = self.path / "data.json" # contain data for restart node

        # condition, node of the registry
        if self.name == self.registry.name:
            self.ip6 = self.registry.ip6
            if not self.crt.exists():
                self.create_node()
        else:
            # if ca file changed, we need recreate node file
            if self.data_file.exists():
                with self.data_file.open() as f:
                    data = json.load(f)
                    self.ip6 = data.get("ip6")
                    recreate = not data.get('hash') == self.registry.ident
            else:
                recreate = True

            if recreate and self.path.exists():
                shutil.rmtree(str(self.path))

            if not self.path.exists():
                self.path.mkdir()
                self.create_node()

        logging.debug("%s's subnet is %s", self.name, self.ip6)

        self.clean()


    def __repr__(self):
        return self.name

    @classmethod
    def generate_name(cls):
        cls.node_seq += 1
        return "node_{}".format(cls.node_seq)

    def create_node(self):
        """create necessary file for node"""
        logging.info("create dir of node %s", self.name)
        cmd = ["--registry", self.registry.url, '--email', self.email]
        cmd = RE6ST_CONF.split() + cmd
        p = self.node.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE,
                            cwd=str(self.path))
        # read token
        db = sqlite3.connect(str(self.registry.db), isolation_level=None)
        count = 0
        token = None
        while not token:
            time.sleep(.1)
            token = db.execute("SELECT token FROM token WHERE email=?",
                               (self.email,)).fetchone()
            count += 1
            if count > 100:
                p.destroy()
                raise Exception("can't connect to the Register")

        out, _ = p.communicate(str(token[0]))
        # logging.debug("re6st-conf output: {}".format(out))
        # find the ipv6 subnet of node
        self.ip6 = re.search('(?<=subnet: )[0-9:a-z]+', out).group(0)
        data = {'ip6': self.ip6, 'hash': self.registry.ident}
        with open(str(self.data_file), 'w') as f:
            json.dump(data, f)
        logging.info("create dir of node %s finish", self.name)

    def run(self, *args):
        """execute re6stnet"""
        cmd = ['--log', self.path, '--run', self.run_path, '--state', self.path,
               '--dh', DH_FILE, '--ca', self.registry.ca_crt, '--cert', self.crt,
               '--key', self.key, '-v4', '--registry', self.registry.url,
               '--console', self.console]
        cmd = map(str, cmd)
        cmd = RE6STNET.split() + cmd

        cmd += args
        logging.debug("run node %s at ns: %s with cmd: %s",
                     self.name, self.node.pid, " ".join(cmd))
        self.proc = self.node.Popen(cmd, stdout=PIPE, stderr=PIPE)

    def clean(self):
        """remove the file created last time"""
        for name in ["re6stnet.log", "babeld.state", "cache.db", "babeld.log"]:
            f = self.path / name
            try:
                f.unlink()
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise

    def stop(self):
        """stop running re6stnet process"""
        logging.debug("%s teminate process %s", self.name, self.proc.pid)
        self.proc.destroy()


    def __del__(self):
        """teminate process and rm temp dir"""
        try:
            self.stop()
        except Exception as e:
            logging.warn("%s: %s", self.name, e)

        # python2 seems auto clean the tempdir
        # try:
        #     shutil.rmtree(self.run_path)
        # except Exception as e:
        #     logging.error("{}: {}".format(self.name, e))
