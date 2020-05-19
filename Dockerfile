FROM mixtt_base:latest

COPY etc/ /etc

WORKDIR /mixtt

COPY . .
