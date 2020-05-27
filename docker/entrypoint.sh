#!/bin/bash

service openvswitch-switch start
ovs-vsctl set-manager ptcp:6640

faucet &> /dev/null &

sleep 2

cd /mixtt

./setup.py install &>/dev/null

sleep 2

cd docker/ixpmfc

python3 ixpmfc.py && \
cp faucet.yaml /etc/faucet/faucet.yaml && \
cp topology.json /etc/mixtt/topology.json && \
cd /mixtt && \
mixtt
