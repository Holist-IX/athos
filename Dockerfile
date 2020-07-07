FROM mixtt_base:latest

COPY etc/ /etc

WORKDIR /mixtt

COPY . .

EXPOSE 80/udp
EXPOSE 80/tcp
