# Athos

## What is Athos?
Athos is an automated network emulator that tests for reachability and redundancy for network. It is build on top of the popular Mininet framework with added P4 software switch support by making use of bmv2.

It takes in a JSON file and build a network based on this, tests reachability over IPv4, IPv6 and is vlan aware between hosts and tests for redundancy availability between switches. 

## Installation

The currently supported methods for installing Athos are 1) using the provided docker build that contains all the dependencies and requirements or 2) manually building setting up an installation on Ubuntu.

1. Docker

    1.1 Docker Compose
    
    If you have docker compose installed, the simplest way would be to run the `run_docker.sh` script, you can add `output` as an optional variable if you want feedback when Athos is running. This will build the Athos docker as well as run it to ensure everything is working.

    This will mount `etc/mixtt` and `etc/faucet` into the docker container.

    1.2 Pure Docker
    
    If you would prefer using just docker, you can build it using `docker build mixtt:latest .` in the install directory.

    To run it you can run the following:

    `docker run -it --privileged mixtt`

    This will run Athos with the example network topology, running 4 OpenFlow Open vSwitches configured via faucet and 2 bmv2 switches running p4 compiled umbrella code.

2. Build natively
   
    Only recommended if you really want to run Athos natively on your system and want to develop and compile your own P4 switch. Be aware that the bmv2 section can take upwards of 5 hours to compile and build, and tend to have problems on Ubuntu 20.04+.

    Install the following and all their dependencies.

    * Python 3.7+
    * [Mininet](https://github.com/mininet/mininet/blob/master/INSTALL)
    * [Faucet](https://docs.faucet.nz/en/latest/installation.html)
    * [bmv2](https://github.com/p4lang/behavioral-model)


    Finally to install Athos you can run `python3 -m pip install .` within the repo directory.


## Configuration

The main configuration lies within `/etc/mixtt/topology.json`. This contains the topology information for Athos to emulate.

Below is a sample config containing 2 hosts connected to 2 OpenFlow edge switches with a bmv2 switch acting as the core switch. By default Athos comes with a compiled bmv2 that does switching based on the [Umbrella concept](https://hal.archives-ouvertes.fr/hal-01862776)


``` json
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
    },
  ],
  "switch_matrix": {
    "dp_ids": { "s1": 1, "s2": 2, },
    "links": [
      ["s1", "10", "s3", "10"],
      ["s2", "11", "s3", "11"],
    ],
    "p4": ["s3"]
  }
}
```

