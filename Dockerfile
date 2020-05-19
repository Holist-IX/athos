FROM mixtt_base:latest

COPY etc/ /etc

WORKDIR /mixtt

COPY . .

ENTRYPOINT ./docker/entrypoint.sh