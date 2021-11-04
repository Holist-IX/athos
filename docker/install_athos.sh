#!/bin/bash

apt update
apt install -y --no-install-recommends git openvswitch-switch iputils-ping mininet net-tools gcc iproute2
apt upgrade -y
pip3 -q --no-cache-dir install --upgrade pip wheel setuptools mininet



if [ -n "$1" ] && [ "$1" == 'faucet' ]; then
        pip3 -q --no-cache-dir install --upgrade faucet
        cp /athos
else
    pip3 -q --no-cache-dir install --upgrade cerberus-controller
    cp /athos/etc/athos/topology.json /etc/cerberus/topology.json
fi
pip3 install .
ln /bin/sed /usr/bin/sed

mkdir /etc/athos
mkdir /var/log/athos
cp /athos/etc/athos/topology.json /etc/athos/topology.json
cp /athos/etc/athos/umbrella.json /etc/athos/umbrella.json
# Needed to make tcpdump working within docker
mv /usr/sbin/tcpdump /usr/bin/tcpdump
ln -s /usr/bin/tcpdump /usr/sbin/tcpdump

apt purge -y gcc git
apt clean -y
apt autoremove -y
rm -rf /var/lib/apt/lists/*