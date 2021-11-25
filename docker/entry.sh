#!/bin/bash
OUT_FILE=/athos/ixpman_files/output.txt

service openvswitch-switch start 2>&1 | tee $OUT_FILE
ovs-vsctl set-manager ptcp:6640 2>&1 | tee -a $OUT_FILE
if [ -n "$1" ] && [ "$1" == 'faucet' ]; then
    faucet 2>&1 | tee -a $OUT_FILE &
else
    cp /etc/athos/topology.json /etc/cerberus/topology.json
    cerberus-controller 2>&1 | tee -a $OUT_FILE &
fi
# Need to wait a second to give the SDN controller a chance to start up
sleep 1s
athos 2>&1 | tee -a $OUT_FILE

cd ixpman_files
python3 parser.py 2>&1 | tee -a $OUT_FILE
NOW=`date +%Y_%m_%d_%H_%M_%S`
mkdir -p logs
cp output.txt logs/output_$NOW.log