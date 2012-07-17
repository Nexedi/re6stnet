#!/usr/bin/env python
import argparse, errno, math, os, select, subprocess, sys, time, traceback
from OpenSSL import crypto
import db, plib, upnpigd, utils, tunnelmanager

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

    # Launch babel on all interfaces. WARNING : you have to be root to start babeld
    babel = plib.babel(stdout=os.open(os.path.join(utils.config.log, 'vifibnet.babeld.log'), 
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC), stderr=subprocess.STDOUT)

    # Create and open read_only pipe to get connect/disconnect events from openvpn
    utils.log('Creating pipe for server events', 3)
    r_pipe, write_pipe = os.pipe()
    read_pipe = os.fdopen(r_pipe)

    # Setup the tunnel manager
    peers_db = db.PeersDB(utils.config.db)
    tunnelManager = tunnelmanager.TunnelManager(write_pipe, peers_db)

   # Establish connections
    serverProcess = plib.server(utils.config.internal_ip, write_pipe, '--dev', 'vifibnet',
            stdout=os.open(os.path.join(utils.config.log, 'vifibnet.server.log'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC))
    tunnelManager.refresh()

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
                peers_db.populate(100)
                tunnelManager.refresh()
                next_refresh = time.time() + utils.config.refresh_time
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    main()

