#!/bin/bash

apt update
apt install -y --no-install-recommends git openvswitch-switch iputils-ping mininet net-tools gcc iproute2
apt upgrade -y
pip3 -q --no-cache-dir install --upgrade pip wheel setuptools mininet faucet
pip3 install .
ln /bin/sed /usr/bin/sed


cp /athos/etc/faucet/faucet.yaml /etc/faucet/faucet.yaml
mkdir /etc/athos
mkdir /var/log/athos
cp /athos/etc/athos/topology.json /etc/athos/topology.json
cp /athos/etc/athos/umbrella.json /etc/athos/umbrella.json
mv /usr/sbin/tcpdump /usr/bin/tcpdump
ln -s /usr/bin/tcpdump /usr/sbin/tcpdump

apt purge -y gcc git
apt clean -y
apt autoremove -y
rm -rf /var/lib/apt/lists/*