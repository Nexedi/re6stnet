Demo
====

Usage
-----

To run the demo, make sure all the dependencies are installed
and run ``./demo 8000`` (or any port).

Troubleshooting
---------------

If the demo crashes and fails to clean up its resources properly,
run the following commands::

  for b in $(sudo ip l | grep -Po 'NETNS\w\w[\d\-a-f]+'); do sudo ip l del $b; done
  pkill screen
  killall python
  killall python3
  find . -name '*.crt' -delete; find . -name '*.db' -delete; find . -name '*.log' -delete

.. warning::

    This will kill all Python processes. These commands assume you're running
    the demo on a dedicated machine with nothing else on it.
