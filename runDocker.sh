#!/bin/bash
cd `dirname "$0"`

if [ -n "$1" ]; then
    if [ "$1" == 'urge' ]; then
        docker-compose run --entrypoint /athos/docker/entry_urge.sh athosurge .
    else
        docker-compose run athos .
    fi
else
    docker-compose run athos --entrypoint /athos/docker/entry_no_output.sh
fi