import logging, errno, os, subprocess, sys
from . import utils

here = os.path.realpath(os.path.dirname(__file__))
if sys.platform == 'cygwin':
    here = subprocess.check_output(['cygpath', '-m', here]).strip()
    script_ext = '.exe'
else:
    script_ext = ''
ovpn_server = os.path.join(here, 'ovpn-server' + script_ext)
ovpn_client = os.path.join(here, 'ovpn-client' + script_ext)
ovpn_log = None

def openvpn(iface, encrypt, *args, **kw):
    args = ['openvpn',
        '--dev-type', 'tap',
        '--dev-node' if sys.platform == 'cygwin' else '--dev', iface,
        '' if sys.platform == 'cygwin' else '--persist-tun',
        '--persist-key',
        '--script-security', '2',
        '--mute-replay-warnings',
        '--up', ovpn_client,
        #'--user', 'nobody', '--group', 'nogroup',
        ] + list(args)
    if ovpn_log:
        args += '--log-append', os.path.join(ovpn_log, '%s.log' % iface),
    if not encrypt:
        args += '--cipher', 'none'
    logging.debug('%r', args)
    return utils.Popen(args, **kw)


def server(iface, max_clients, dh_path, pipe_fd, port, proto, encrypt, *args, **kw):
    client_script = '%s /proc/%u/fd/%s' % (ovpn_server, os.getpid(), pipe_fd)
    if pipe_fd is not None:
        args = ('--client-disconnect', client_script) + args
    return openvpn(iface, encrypt,
        '--tls-server',
        '--mode', 'server',
        '--client-connect', client_script,
        '--dh', dh_path,
        '--max-clients', str(max_clients),
        '--port', str(port),
        '--proto', 'tcp-server' if proto == 'tcp' else proto,
        *args, **kw)


def client(iface, address_list, encrypt, *args, **kw):
    remote = ['--nobind', '--client']
    for ip, port, proto in address_list:
        remote += '--remote', ip, port, \
            'tcp-client' if proto == 'tcp' else proto
    remote += args
    return openvpn(iface, encrypt, *remote, **kw)


def router(subnet, hello_interval, table, log_path, state_path, pidfile,
           tunnel_interfaces, *args, **kw):
    s = utils.ipFromBin(subnet)
    n = len(subnet)
    cmd = ['babeld',
            '-h', str(hello_interval),
            '-H', str(hello_interval),
            '-L', log_path,
            '-S', state_path,
            '-I', pidfile,
            '-s',
            '-C', 'redistribute local deny',
            '-C', 'redistribute ip %s/%u eq %u' % (s, n, n),
            '-C', 'redistribute deny']
    if table:
        cmd += '-t%u' % table, '-T%u' % table
    else:
        cmd[-2:-2] = '-C', 'redistribute ip ::/0 eq 0'
    for iface in tunnel_interfaces:
        cmd += '-C', 'interface %s rxcost 512' % iface
    cmd += args
    # WKRD: babeld fails to start if pidfile already exists
    try:
        os.remove(pidfile)
    except OSError, e:
        if e.errno != errno.ENOENT:
            raise
    logging.info('%r', cmd)
    return utils.Popen(cmd, **kw)
