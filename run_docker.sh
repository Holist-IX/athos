#!/bin/bash
cd `dirname "$0"`

if [ -n "$1" ]; then
    if [ "$1" == 'urge' ]; then
        docker-compose run -v $URGEDIR:/urge --entrypoint /mixtt/docker/entry_urge.sh mixtt .
    else
    docker-compose run --entrypoint /mixtt/docker/entry.sh mixtt .
    fi
else
    docker-compose run mixtt .
fi