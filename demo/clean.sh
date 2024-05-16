#!/usr/bin/env bash

for b in $(sudo ip l | grep -Po 'NETNS\w\w[\d\-a-f]+'); do sudo ip l del $b; done
pkill screen
killall python
killall python3
find . -name '*.db' -delete
find . -name '*.crt' -delete
