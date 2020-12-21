#!/bin/bash
cd `dirname "$0"`

if [ -n "$1" ]; then
    docker-compose run --entrypoint /mixtt/docker/entry.sh mixtt .
else
    docker-compose run mixtt .
fi