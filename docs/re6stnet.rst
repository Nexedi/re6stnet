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
  use ``--default`` option).
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

Starting re6st automatically
----------------------------

If the `/etc/re6stnet/re6stnet.conf` configuration file exists, `re6stnet` is
automatically started as a daemon. This is done is 2 different ways, depending
on whether it is bound or not to a specific interface, by using the
`main-interface` option:

- If the option is not given (or if it is set to 'lo'), then it is automatically
  started/stopped by ``systemd``\ (1). Debian package also provides SysV init
  scripts.

- Otherwise, it is automatically started/stopped when the related network
  interface is enabled/disabled by ``NetworkManager``\ (8). Debian package also
  provides `ifupdown` scripts.

Important note about NetworkManager
-----------------------------------

It is required to configure properly every connection defined in NetworkManager
because default settings are wrong and conflict with re6st:

- If re6st routes all your IPv6 traffic, using ``--default`` option, then make
  sure to disable IPv6 in NetworkManager.

- Otherwise, the following options must be set in [ipv6] section::

   ignore-auto-routes=true
   never-default=true

  In applets, these options are usually named:

  - Ignore automatically obtained routes (KDE & Gnome)
  - Use only for resources on this connection (KDE)
  - Use this connection only for resources on its network (Gnome)

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

(see ``re6st-registry --help`` for examples to create key/dh files)

The CA email will be used as sender for mails containing tokens.
The registry can now be started::

  re6st-registry --ca ca.crt --key ca.key --mailhost smtp.example.com

The registry uses the builtin HTTP server of Python. For security, it should be
behind a proxy like Apache.

The first registered node should be always up because its presence is used by
all other nodes to garantee they are connected to the network. The registry
also emits UDP packets that are forwarded via a localhost re6st node, and it is
recommended that this is the first one::

  re6st-conf --registry http://localhost/

If `re6st-conf` is run in the directory containing CA files, ca.crt will be
overridden without harm. See previous section for more information to create
a node.

For bootstrapping, you may have to explicitly set an IP in the configuration
of the first node, via the ``--ip`` option. Otherwise, additional nodes won't
be able to connect to it.

TROUBLESHOOTING
===============

When many nodes are saturated or behind unconfigurated NAT, it may take
some time to bootstrap. However, if you really think something goes wrong,
you should first enable OpenVPN logs and increase verbosity:
see commented directives in configuration generated by `re6st-conf`.

A common failure is caused by a misconfigured firewall:

- re6st launches several OpenVPN processes. Those in client mode may connect to
  any TCP/UDP port in IPv4. Server processes only listen to ports specified
  by ``--pp`` option.

- re6st nodes use UDP port 326 to communicate.
  It must be open on all re6st IPv6.

- OpenVPN always aborts due to inactivity timeout when Babel paquets are
  filtered. UDP port 6696 must be open on link-local IPv6 of all interfaces
  managed by Babel.

Other security components may also break re6st. For example, default SELinux
configuration on Fedora prevents execution of OpenVPN server processes.

SEE ALSO
========

``re6st-conf``\ (1), ``re6st-registry``\ (1), ``babeld``\ (8), ``openvpn``\ (8),
``rdisc6``\ (8), ``req``\ (1)
