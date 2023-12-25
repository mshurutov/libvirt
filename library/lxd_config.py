#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2023, Michail Shurutov based on lxd_network by Sofiane Medjkoune <sofiane@medjkoune.fr> based on lxd_profile by Hiroaki Nakamura <hnakamur@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: lxd_config
short_description: Manage LXD config parameters
version_added: "2.15"
description:
  - Management of LXD config parameters
author: "Michail Shurutov"
options:
    config:
        description:
          - 'The config parameters (e.g. {"core.https_address": "192.168.0.1:8443"}).
            See U(https://documentation.ubuntu.com/lxd/en/latest/api/#/server/server_get)
          - If the network already exists and its "config" value in metadata
            obtained from
            GET /1.0/networks/<name>
            U(https://github.com/lxc/lxd/blob/master/doc/rest-api.md#get-16)
            are different, then this module tries to apply the configurations.
          - If either ipv4.address or ipv6.address are not set in the config
            a value of none will be defaulted.
        required: true
        default: {'ipv4.address': none, 'ipv6.address': none}
notes:
  - Networks must have a unique name. If you attempt to create a network
    with a name that already existed in the users namespace the module will
    simply return as "unchanged".
'''

EXAMPLES = '''
# An example for creating a network
- hosts: localhost
  connection: local
  tasks:
    - name: Create a network
      lxd_network:
        name: lxdbr0
        state: present
        config:
          ipv4.address: none
          ipv6.address: 2001:470:b368:4242::1/64
          ipv6.nat: "true"
        description: My network

# An example for creating a network via http connection
- hosts: localhost
  connection: local
  tasks:
  - name: create lxdbr0 bridge
    lxd_network:
      url: https://127.0.0.1:8443
      # These cert_file and key_file values are equal to the default values.
      #cert_file: "{{ lookup('env', 'HOME') }}/.config/lxc/client.crt"
      #key_file: "{{ lookup('env', 'HOME') }}/.config/lxc/client.key"
      trust_password: mypassword
      name: lxdbr0
      state: present
      config:
        bridge.driver: openvswitch
        ipv4.address: 10.0.3.1/24
        ipv6.address: fd1:6997:4939:495d::1/64
      description: My network

# An example for deleting a network
- hosts: localhost
  connection: local
  tasks:
    - name: Delete a network
      lxd_network:
        name: lxdbr0
        state: absent

# An example for renaming a network
- hosts: localhost
  connection: local
  tasks:
    - name: Rename a network
      lxd_network:
        name: lxdbr0
        new_name: lxdbr1
        state: present
'''

RETURN = '''
old_state:
  description: The old state of the network
  returned: success
  type: string
  sample: "absent"
logs:
  description: The logs of requests and responses.
  returned: when ansible-playbook is invoked with -vvvv.
  type: list
  sample: "(too long to be placed here)"
actions:
  description: List of actions performed for the network.
  returned: success
  type: list
  sample: '["create"]'
'''

import os

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.lxd import LXDClient, LXDClientException


