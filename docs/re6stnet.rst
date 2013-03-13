==========
 re6stnet
==========

---------------------------------------------
Resilient, Scalable, IPv6 Network application
---------------------------------------------

:Author: Nexedi
:Manual section: 8

SYNOPSIS
========

``re6stnet`` ``--registry`` `registry-url` ``--dh`` `dh-path`
``--ca`` `ca-path` ``--cert`` `cert-path` ``--key`` `key-path`
[`options`...] [``--`` [`openvpn-options`...]]

DESCRIPTION
===========

`re6stnet` runs a node of a re6st network. It establishes connections
with other nodes by creating OpenVPN tunnels and uses Babel for routing.

USAGE
=====

Use ``re6stnet --help`` to get the complete list of options.

If you already have IPv6 connectivity by autoconfiguration and still want to
use it for communications that are unrelated to this network, then:

- your kernel must support source address based routing (because you can't
  use ``--table 0`` option).
- you must set ``net.ipv6.conf.<iface>.accept_ra`` sysctl to value 2 and
  trigger SLAAC with ``rdisc6 <iface>`` to restore the default route if the
  kernel removed while enabling forwarding.

Following environment variables are available for processes started with
``--up`` or ``--daemon``:

re6stnet_iface
  value of ``--main-interface`` option
re6stnet_ip
  IPv6 set on main interface
re6stnet_subnet
  your subnet, written in CIDR notation
re6stnet_network
  the re6st network you belong to, written in CIDR notation

HOW TO
======

Joining an existing network
---------------------------

Once you know the registry URL of an existing network, use `re6st-conf` to get
a certificate::

  re6st-conf --registry http://re6st.example.com/

Use `-r` option to add public information to your certificate.
A token will be sent to the email you specify, in order to confirm your
subscription.
Files will be created by default in current directory and they are all
required for `re6stnet`::

  re6stnet --dh dh2048.pem --ca ca.crt --cert cert.crt --key cert.key \
           --registry http://re6st.example.com/

Setting a new network
---------------------

First you need to know the prefix of your network: let's suppose it is
`2001:db8:42::/48`. From it, you computes the serial number of the Certificate
authority (CA) that will be used by the registry node to sign delivered
certificates, as follows: translate the significant part to hexadecimal
(ie. 20010db80042) add a **1** as the most significant digit::

  openssl req -nodes -new -x509 -key ca.key -set_serial 0x120010db80042 \
              -days 365 -out ca.crt

The CA email will be used as sender for mails containing tokens.

Now start the registry in order to setup the main re6st node, which should be
on the same machine::

  re6st-registry --ca ca.crt --key ca.key --mailhost smtp.example.com
  re6st-conf --registry http://localhost/

If `re6st-conf` is run in the directory containing CA files, ca.crt will be
overridden without harm.

Note that the registry was started without specifying the re6st IP of the main
node, because it was not known yet. For your network to work, it has to be
restarted with appropriate --private option.

Let's suppose your first node is allocated subnet 2001:db8:42::/64.
Its IP is the first unicast address::

  re6st-registry --private 2001:db8:42::1 ...
  re6stnet --registry http://localhost/ --ip re6st.example.com ...

SEE ALSO
========

``re6st-conf``\ (1), ``re6st-registry``\ (1), ``babeld``\ (8), ``openvpn``\ (8)
