==========
 re6stnet
==========

---------------------------------------------
Resilient, Scalable, IPv6 Network application
---------------------------------------------

:Contact: Julien Muchembled <jm@nexedi.com>

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

Building an ipv4 network is also supported if one has software that does not
support ipv6.

How to pronounce `re6st`? Like `resist`.

HOW IT WORKS
============

A re6stnet network consists of at least one server (re6st-registry) and many
nodes (re6stnet). The server is only used to deliver certificates for secure
authentication of peers, and to bootstrap new nodes.
re6stnet can detect and take into account nodes present on the local network.

Resilience
----------
re6stnet guarantees that if there exists a route between two machines,
traffic will be correctly routed between these two machines.
Even if the registry node is down, the probability that the network is not
connected is very low for big enough networks (more than a hundred nodes).

Scalability
-----------

Since nodes don't need to know the whole graph of the network, re6stnet is
easily scalable to tens of thousand of nodes.

Requirements
============

- Python 2.6 or 2.7
- OpenSSL binary and development libraries
- OpenVPN >= 2.3
- Babel_ (with Nexedi patches)
- python-miniupnpc for UPnP support (optional)
- for the demo: miniupnpd_, Graphviz, Screen_, Nemu_

See also `setup.py` for Python dependencies.

.. _Babel: https://lab.nexedi.com/nexedi/babeld
.. _Nemu: https://github.com/thetincho/nemu
.. _miniupnpd: http://miniupnp.free.fr/
.. _Screen: http://savannah.gnu.org/projects/screen

Installation
============

| Official packaging is implemented at
|   https://lab.nexedi.com/nexedi/slapos.package/tree/master/obs/re6st
| and packages are built for many Linux distributions at
|   https://build.opensuse.org/package/show/home:VIFIBnexedi/Re6stnet

| re6stnet is also distributed as a Python egg:
|   https://pypi.python.org/pypi/re6stnet

References
==========

| Building a resilient overlay network : Re6stnet
|   http://www.j-io.org/P-ViFiB-Resilient.Overlay.Network/Base_download
| GrandeNet - The Internet on Steroids
|   https://www.nexedi.com/blog/NXD-Document.Blog.Grandenet.Internet.On.Steroids
| Grandenet success case
|  https://www.nexedi.com/success/erp5-GKR.Success.Case
| n-Order Re6st - Achieving Resiliency and Scaliblity
|  https://www.nexedi.com/blog/NXD-Document.Blog.N.Order.Res6st.Resiliency.And.Scalability

Usage
=====

See ``re6stnet``\ (8) man page.
