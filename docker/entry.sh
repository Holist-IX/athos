#!/bin/bash

service openvswitch-switch start
ovs-vsctl set-manager ptcp:6640
faucet &
sleep 1s
mixtt