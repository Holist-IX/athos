# Athos

## What is Athos?

Athos is an automated network emulator that tests for reachability and
redundancy for network. It is build on top of the popular Mininet framework
with added P4 software switch support by making use of bmv2.

It takes in a JSON file and build a network based on this, tests reachability
over IPv4, IPv6 and is vlan aware between hosts and tests for redundancy
availability between switches.

## Installation

The currently supported methods for installing Athos are 1) using the provided
docker build that contains all the dependencies and requirements or 2) manually
building setting up an installation on Ubuntu.

1. Pip

  Athos can be installed via `pip3 install athos`.

  Do note that if you want to use the p4 core element, you will need to follow
  the instructions for building it natively, as bmv2 and its dependencies are
  required.

2. Docker

   2.1 Dockerhub

   You can pull it using `docker pull belthazaar/athos`

   Running it through `docker run --privileged belthazaar/athos` will run athos
   with the example configs for athos and faucet.

   To run your configs you will need to mount the faucet and athos configs at
   `/etc/faucet/` and `/etc/athos/` respectively.

   2.2 Docker Compose

   If you have docker compose installed, the simplest way would be to run the
   `runDocker.sh` script. This will build the Athos docker as well as run it
   to ensure everything is working.

   This will mount `etc/athos` and `etc/faucet` into the docker container.

   2.3 Pure Docker

   If you preferred using just docker, you can build it using
   `docker build belthazaar/athos:latest .` in the install directory.

   To run it you can run the following:

   `docker run -it --privileged belthazaar/athos`

   This will run Athos with the example network topology, running 4 OpenFlow
   Open vSwitches configured via faucet and 2 bmv2 switches running p4
   compiled umbrella code.

3. Build natively

   Only recommended if you really want to run Athos natively on your system
   and want to develop and compile your own P4 switch. Be aware that the bmv2
   section can take upwards of 5 hours to compile and build, and tend to have
   problems on Ubuntu 20.04+.

   Install the following and all their dependencies.

   - Python 3.7+
   - [Mininet](https://github.com/mininet/mininet/blob/master/INSTALL)
   - [Faucet](https://docs.faucet.nz/en/latest/installation.html)
   - [bmv2](https://github.com/p4lang/behavioral-model)

   Finally, to install Athos you can run `python3 -m pip install .` within the
   repo directory.

## Configuration

The main configuration lies within `/etc/athos/topology.json`. This contains
the topology information for Athos to emulate. A topology file can also be
declared using the `-t` option. By default, Athos will look in `/etc/athos`
for the topology and the P4 JSON files.

Below is a sample config containing 2 hosts connected to 2 OpenFlow edge
switches with a bmv2 switch acting as the core switch. By default, Athos comes
with a compiled bmv2 that does layer-2 switching based on the
[Umbrella concept](https://hal.archives-ouvertes.fr/hal-01862776)

```json
{
  "hosts_matrix": [
    {
      "name": "h1",
      "interfaces": [
        {
          "vlan": "200",
          "ipv4": "10.0.0.1/24",
          "ipv6": "fd00::1/64",
          "mac": "00:00:00:00:00:01",
          "swport": 1,
          "switch": "s1"
        }
      ]
    },
    {
      "name": "h2",
      "interfaces": [
        {
          "vlan": "200",
          "ipv4": "10.0.0.2/24",
          "ipv6": "2001:db8:::2/64",
          "mac": "00:00:00:00:00:02",
          "swport": 1,
          "switch": "s2"
        }
      ]
    }
  ],
  "switch_matrix": {
    "dp_ids": { "s1": 1, "s2": 2 },
    "links": [
      ["s1", "10", "s3", "10"],
      ["s2", "11", "s3", "11"]
    ],
    "p4": ["s3"]
  }
}
```

### Faucet

By default, Athos is designed to work with Faucet as the controller for the
OpenFlow switches. A sample config has been provided in
`etc/faucet/faucet.yaml`, with rules provided to work with the Umbrella bmv2
core. The included faucet install is unchanged within the docker containers, so
any configuration can be used, however do note that it can cause problems if
used with the default bmv2 switches that does switching based on MAC shifting.

### bmv2

Athos by default uses an Umbrella core switch for it's P4 switches. This is
compiled using bmv2, based on their `simple_switch` and the resulting JSON that
tells the switch how to implement its packet processing. This JSON is located
at `/etc/athos/umbrella.json` however you can use the `--p4-json` option to
declare another compiled P4 JSON file.

Currently, there is no support for topologies with bmv2 switches running
different P4 code to one another, however support could be added later if
there is enough interest.

## Usage

Athos can be run using `sudo athos`. This will start up a network based on the
topology information, check reachability between hosts over ipv4 and ipv6 and
per vlan. This assumes that faucet is running has been configured.

Below are some of the optional arguments that can be used:

| Argument                                        | Description                                                |
| ----------------------------------------------- | ---------------------------------------------------------- |
| -t TOPOLOGY_FILE, --topology-file TOPOLOGY_FILE | Reads topology information from a JSON file                |
| -c, --cli                                       | Enables CLI for debugging                                  |
| -p PING, --ping PING                            | Set the ping count used in pingall                         |
| -n, --no-redundancy                             | Disables the link redundancy checker (Used for testing p4) |
| --thrift-port THRIFT_PORT                       | Thrift server port for p4 table updates                    |
| --p4-json P4_JSON                               | Config json for p4 switches                                |
| --script SCRIPT                                 | Runs a script before doing standard testing                |
