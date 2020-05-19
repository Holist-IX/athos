#!/bin/bash

service openvswitch-switch start
ovs-vsctl set-manager ptcp:6640

faucet &

sleep 2

mixtt