#!/bin/bash
cd `dirname "$0"`
URGEDIR=/home/ixpman/code/urge

if [ -n "$1" ]; then
    if [ "$1" == 'urge' ]; then
        docker-compose run -v $URGEDIR:/urge --entrypoint /athos/docker/entry_urge.sh athos .
    else
        docker-compose run athos .
    fi
else
    docker-compose run athos --entrypoint /athos/docker/entry_no_output.sh
fi