==========
 re6stnet
==========

---------------------------------------------
Resilient, Scalable, IPv6 Network application
---------------------------------------------

:Author: Nexedi <re6stnet@erp5.org>

Overview
========

re6stnet creates a resilient, scalable, ipv6 network on top of an existing ipv4
network, by creating tunnels on the fly, and then routing targeted traffic
through these tunnels.

re6stnet can be used to:

- guarantee connectedness between computers connected to the
  internet, for which there exists a working route (in case the direct route
  isn't available).
- create large networks
- give ipv6 addresses to machines with only ipv4 available

HOW IT WORKS
============

A re6stnet network consists of at least one server (re6st-registry) and many
nodes (re6stnet). The server is only used to deliver certificates for secure
authentification in establishing tunnels, and to bootstrap new nodes.
re6stnet can detect and take into account nodes present on the local network.

Resilience
----------
re6stnet guarantees that if there exists a route between two machines,
traffic will be correctly routed between these two machines.
Even if the registry node is down, the probability that the network isn't
connected is very low for big enough networks (more than a hundred nodes).

Scalability
-----------

Since each node has very few data about the network, re6stnet is easily
scalable to tens of thousand of nodes

Requirements
============

- Python 2.6 or 2.7
- OpenSSL binary and development libraries
- OpenVPN
- Babel_ (with Nexedi patches)
- python-miniupnpc for UPnP support (optional)
- for the demo: miniupnpd_, Graphviz, Screen, Nemu_

See also `setup.py` for Python dependencies.

.. _Babel: http://git.erp5.org/gitweb/babeld.git
.. _Nemu: http://code.google.com/p/nemu/
.. _miniupnpd: http://miniupnp.free.fr/

Installation
============

re6stnet is distributed as a Python egg, and is also packaged for DEB & RPM
based distributions:

See `re6st-registry` to set up a re6st network
and `re6st-conf` to join an existing network.

On Debian Squeeze, you will have to install `babeld` package from Wheezy.

In order to build DEB snapshot package whose version is derived from current
Git revision, the `debian/changelog` file must be generated automatically,
that's why you can't use `dpkg-buildpackage` directly: run ``debian/rules``
instead. RPM does not have this limitation: do `rpmbuild -bb re6stnet.spec``
as usual.
