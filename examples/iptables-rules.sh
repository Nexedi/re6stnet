#!/bin/sh
#
# Example iptables/ip6tables rules on a desktop computer when re6st is only
# used to build an IPv6 overlay network. REJECT everything by default:
#
# - Incoming traffic (INPUT): only open ports needed for re6st and also allow
#   packets associated with an existing connection (ESTABLISHED, RELATED).
#
# - Forwarding traffic (FORWARD): a re6st node is a router and
#   it is crucial that it never drops any packet between two other nodes.
#
# - Outgoing traffic (OUTPUT): allow new/existing connections (NEW,
#   ESTABLISHED, RELATED).
#
# WARNING: THIS SCRIPT *MUST NOT* JUST BE COPY-PASTED WITHOUT A BASIC
#          UNDERSTANDING OF IPTABLES/IP6TABLES (see iptables(8) and
#          iptables-extensions(8) manpages).

GATEWAY_IP=192.168.0.1

## IPv4
iptables -P INPUT REJECT
iptables -P OUTPUT REJECT

iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A INPUT -p icmp --icmp-type echo-request -m limit --limit 900/min -j ACCEPT
iptables -A INPUT -p icmp --icmp-type echo-reply -m limit --limit 900/min -j ACCEPT
# re6st
iptables -A INPUT -p tcp -m tcp --dport 1194 -j ACCEPT
# UPnP
iptables -A INPUT -p udp -m udp --sport 1900 -s $GATEWAY_IP -j ACCEPT

iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -m state --state NEW,RELATED,ESTABLISHED -j ACCEPT

# more rules needed if you set up a private IPv4 network

## IPv6
ip6tables -P INPUT REJECT
ip6tables -P FORWARD REJECT
ip6tables -P OUTPUT REJECT

ip6tables -N RE6ST
ip6tables -A RE6ST -i re6stnet+ -j ACCEPT
# For every --interface option:
ip6tables -A RE6ST -i eth0 -j ACCEPT

ip6tables -A INPUT -i lo -j ACCEPT
ip6tables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
ip6tables -A INPUT -p udp -m udp --dport babel --src fe80::/10 -j ACCEPT
# Babel
ip6tables -A INPUT -p udp -m udp --dport 326 -j RE6ST
ip6tables -A INPUT -p ipv6-icmp -m icmp6 --icmpv6-type destination-unreachable -j ACCEPT
ip6tables -A INPUT -p ipv6-icmp -m icmp6 --icmpv6-type packet-too-big -j ACCEPT
ip6tables -A INPUT -p ipv6-icmp -m icmp6 --icmpv6-type time-exceeded -j ACCEPT
ip6tables -A INPUT -p ipv6-icmp -m icmp6 --icmpv6-type parameter-problem -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-request -m limit --limit 900/min -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type echo-reply -m limit --limit 900/min -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbor-solicitation -m hl --hl-eq 255 -j ACCEPT
ip6tables -A INPUT -p icmpv6 --icmpv6-type neighbor-advertisement -m hl --hl-eq 255 -j ACCEPT

ip6tables -A FORWARD -o re6stnet+ -j RE6ST
# Same as in RE6ST chain.
ip6tables -A FORWARD -o eth0 -j RE6ST

ip6tables -A OUTPUT -o lo -j ACCEPT
ip6tables -A OUTPUT -m state --state NEW,RELATED,ESTABLISHED -j ACCEPT
ip6tables -A OUTPUT -p ipv6-icmp -m icmp6 --icmpv6-type destination-unreachable -j ACCEPT
ip6tables -A OUTPUT -p ipv6-icmp -m icmp6 --icmpv6-type packet-too-big -j ACCEPT
ip6tables -A OUTPUT -p ipv6-icmp -m icmp6 --icmpv6-type time-exceeded -j ACCEPT
ip6tables -A OUTPUT -p ipv6-icmp -m icmp6 --icmpv6-type parameter-problem -j ACCEPT
ip6tables -A OUTPUT -p icmpv6 --icmpv6-type neighbor-solicitation -m hl --hl-eq 255 -j ACCEPT
ip6tables -A OUTPUT -p icmpv6 --icmpv6-type neighbor-advertisement -m hl --hl-eq 255 -j ACCEPT
