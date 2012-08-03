================
 re6st-registry
================

--------------------------------
 Server application for re6snet
--------------------------------

:Author: Nexedi
:Manual section: 1

SYNOPSIS
========

``re6st-registry`` `port` ``--db`` `db-path` ``--ca`` `ca-path`
``--key`` `key-path` ``--mailhost`` `mailhost` ``--private`` `private-ip`
[`options`...]

DESCRIPTION
===========

re6st-registry is a server for the re6st network. Its role is to deliver
vertificates to new nodes, and to maintain the complete table of peers, so it
can send part of it to nodes asking for new peers.
As of now, only one re6st-registry per re6st network should run. The node
running the re6st-registry must also have a client ( re6stnet ) running.

USAGE
=====

The re6st-registry will automatically listen on both ipv4 and ipv6 for incomming
request.

port
            The port on which the server will listen

--db path
            Path to the server Database file. A new DB file will be created
            and correctly initialized if the file doesn't exists.
            One can give ":memory" as path, the database is then temporary

--ca path
            Path to the certificate authority file. The certificate authority
            MUST contain the VPN network prefix in its serial number. To
            generate correct ca and key files for the 2001:db8:42:: prefix,
            the following command can be used :
            openssl req -nodes -new -x509 -key ca.key -set_serial \
                    0x120010db80042 -days 365 -out ca.crt

--key path
            Path to the server key file. To generate a key file, see the --ca
            option

--mailhost mailhost
            Mailhost to be used to send email containing token for registration

--private ip
            Ipv6 address of the re6stnet client running on the machine. This
            address will be advertised only to nodes having a valid
            certificate.

Options
-------


--bootstrap prefix ip port proto
            Connection informations of a node given to other as a bootstrap
            node to initiate connection with the network.
            Prefix should be the prefix number of a node, given in binary and
            with correct length. For instance the VPN address
            2001:db8:42:1::/64 ( asusming a network prefix 2001:db8:42::/48 )
            corresponds to a prefix 1/16 i.e 0000000000000001.

SEE ALSO
========

``re6stnet``\ (1), ``re6st-conf``\ (1)
