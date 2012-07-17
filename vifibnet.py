#!/usr/bin/env python
import argparse, errno, math, os, select, subprocess, sys, time
from OpenSSL import crypto
import traceback
import upnpigd
import openvpn
import utils
import db
import tunnelmanager

def startBabel(**kw):
    args = ['babeld',
            '-C', 'redistribute local ip %s' % (utils.config.internal_ip),
            '-C', 'redistribute local deny',
            # Route VIFIB ip adresses
            '-C', 'in ip %s::/%u' % (utils.ipFromBin(utils.config.vifibnet), len(utils.config.vifibnet)),
            # Route only addresse in the 'local' network,
            # or other entire networks
            #'-C', 'in ip %s' % (config.internal_ip),
            #'-C', 'in ip ::/0 le %s' % network_mask,
            # Don't route other addresses
            '-C', 'in deny',
            '-d', str(utils.config.verbose),
            '-s',
            ]
    if utils.config.babel_state:
        args += '-S', utils.config.babel_state
    args = args + ['vifibnet'] + list(tunnelmanager.free_interface_set)
    if utils.config.verbose >= 5:
        print args
    return subprocess.Popen(args, **kw)

def handle_message(msg):
    script_type, arg = msg.split()
    if script_type == 'client-connect':
        utils.log('Incomming connection from %s' % (arg,), 3)
        # TODO: check if we are not already connected to it
    elif script_type == 'client-disconnect':
        utils.log('%s has disconnected' % (arg,), 3)
    elif script_type == 'route-up':
        # TODO: save the external ip received
        utils.log('External Ip : ' + arg, 3)
    else:
        utils.log('Unknow message recieved from the openvpn pipe : ' + msg, 1)

def main():
    # Get arguments
    utils.getConfig()
    
    # Setup database
    tunnelmanager.peers_db = db.PeersDB(utils.config.db)

    # Launch babel on all interfaces. WARNING : you have to be root to start babeld
    utils.log('Starting babel', 3)
    babel = startBabel(stdout=os.open(os.path.join(utils.config.log, 'vifibnet.babeld.log'), 
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC), stderr=subprocess.STDOUT)

    # Create and open read_only pipe to get connect/disconnect events from openvpn
    utils.log('Creating pipe for openvpn events', 3)
    r_pipe, write_pipe = os.pipe()
    read_pipe = os.fdopen(r_pipe)

    # Establish connections
    utils.log('Starting openvpn server', 3)
    serverProcess = openvpn.server(utils.config.internal_ip, write_pipe, '--dev', 'vifibnet',
            stdout=os.open(os.path.join(utils.config.log, 'vifibnet.server.log'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC))
    tunnelmanager.startNewConnections(utils.config.client_count, write_pipe)

    # Timed refresh initializing
    next_refresh = time.time() + utils.config.refresh_time

    # main loop
    try:
        while True:
            ready, tmp1, tmp2 = select.select([read_pipe], [], [],
                    max(0, next_refresh - time.time()))
            if ready:
                handle_message(read_pipe.readline())
            if time.time() >= next_refresh:
                tunnelmanager.peers_db.populate(10)
                tunnelmanager.refreshConnections(write_pipe)
                next_refresh = time.time() + utils.config.refresh_time
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    main()

