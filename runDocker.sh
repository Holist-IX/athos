#!/bin/bash
cd `dirname "$0"`

if [ -n "$1" ]; then
    if [ "$1" == 'urge' ]; then
        docker-compose run athos_urge .
    elif [ "$1" == 'no_output' ]; then
        docker-compose run athos .
    elif [ "$1" == 'faucet' ]; then
        docker-compose run athos_faucet .
    fi
else
    docker-compose run athos .
fi