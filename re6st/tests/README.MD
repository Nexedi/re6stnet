If you clone this repo directly, you should add re6stnet to PYTHONPATH, so
python can find module re6st

To run all the tests, you have two methods: one is by creating a new user
namespace, the other is by using root privileges.


* `unshare -Unr bash -c "mount -t sysfs /sys & python -m unittest discover"`
* `python -m unittest discover`

The mount of /sys is because nemu will read files in /sys.
When creating a new network namespace, the exiting network devices will not
disappear, and a re-mount is needed to update /sys.

If you want to only run the unit tests  `python -m unittest discover` is ok,
the network tests will be skipped.
