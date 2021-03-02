FROM ubuntu:16.04 as builder

RUN apt-get update && apt-get install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev wget

WORKDIR /tmp

RUN wget https://www.python.org/ftp/python/3.8.6/Python-3.8.6.tar.xz && tar -xf Python-3.8.6.tar.xz && cd /tmp/Python-3.8.6 && ./configure --enable-optimizations && make && make DESTDIR=/output install

FROM p4lang/behavioral-model

WORKDIR /athos

COPY . .

COPY --from=builder output/usr/local /usr/local/

RUN ./docker/install_athos.sh

ENTRYPOINT ./docker/entry.sh