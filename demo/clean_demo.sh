#!/bin/bash

git clean -xf

for i in ${screen_patterns[@]}
do
  screen -wipe $i;
done;

ip link|grep NETNS|awk '{print $2;}'|sed 's/.$//'|sed -E 's/(.*)@.*/\1/g'|xargs -I if ip link del dev if;
