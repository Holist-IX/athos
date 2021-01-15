#!/bin/bash

apt update
apt install -y --no-install-recommends git openvswitch-switch iputils-ping mininet net-tools gcc iproute2
apt upgrade -y
# apt-get install --upgrade python3
pip3 -q --no-cache-dir install --upgrade pip wheel setuptools mininet faucet
# pip3 -q --no-cache-dir install --upgrade /mixtt
cd ..
pip3 install mixtt/
ln /bin/sed /usr/bin/sed


cp /mixtt/etc/faucet/faucet.yaml /etc/faucet/faucet.yaml
mkdir /etc/mixtt
mkdir /var/log/mixtt
cp /mixtt/etc/mixtt/topology.json /etc/mixtt/topology.json
cp /mixtt/etc/mixtt/umbrella.json /etc/mixtt/umbrella.json
mv /usr/sbin/tcpdump /usr/bin/tcpdump
ln -s /usr/bin/tcpdump /usr/sbin/tcpdump

apt purge -y gcc git
apt clean -y
apt autoremove -y
rm -rf /var/lib/apt/lists/*