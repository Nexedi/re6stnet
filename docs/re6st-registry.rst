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

``re6st-registry`` ``--db`` `db-path`  ``--ca`` `ca-path` ``--key`` `key-path`
``--mailhost`` `mailhost` ``--private`` `re6st-ip` [`options`...]

DESCRIPTION
===========

re6st-registry is a server for the re6st network. Its role is to deliver
certificates to new nodes, and to bootstrap nodes that don't know any address
of other nodes.

The network can host only one registry, which should run on a re6st node.

USAGE
=====

Use ``re6st-registry --help`` to get the complete list of options.

The network prefix can be changed by renewing the Certificate authority with
a different serial number, but keeping the existing key. Then all nodes of the
network must fetch the new CA with `re6st-conf` and restart `re6stnet`.

SEE ALSO
========

``re6stnet``\ (8)
