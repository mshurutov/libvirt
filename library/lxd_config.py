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
    client_cert:
        description:
          - The client certificate file path.
        required: false
        default: '"{}/.config/lxc/client.crt" .format(os.environ["HOME"])'
        aliases: [ cert_file ]
    client_key:
        description:
          - The client certificate key file path.
        required: false
        default: '"{}/.config/lxc/client.key" .format(os.environ["HOME"])'
        aliases: [ key_file ]
    config:
        description:
          - 'The config parameters (e.g. {"core.https_address": "192.168.0.1:8443"}).
            See U(https://documentation.ubuntu.com/lxd/en/latest/server/)
          - If "config" value in metadata obtained from
            GET /1.0
            U(https://github.com/canonical/lxd/blob/main/doc/rest-api.md)
            are different, then this module tries to apply the configurations.
          - If either ipv4.address or ipv6.address are not set in the config
            a value of none will be defaulted.
        required: true
        default: {'ipv4.address': none, 'ipv6.address': none}
    trust_password:
        description:
          - The client trusted password.
          - You need to set this password on the LXD server before
            running this module using the following command.
            lxc config set core.trust_password <some random password>
            See U(https://www.stgraber.org/2016/04/18/lxd-api-direct-interaction/)
          - If trust_password is set, this module send a request for
            authentication before sending any requests.
        required: false
    url:
        description:
          - The unix domain socket path or the https URL for the LXD server.
        required: false
        default: unix:/var/lib/lxd/unix.socket
notes:
  - Networks must have a unique name. If you attempt to create a network
    with a name that already existed in the users namespace the module will
    simply return as "unchanged".
'''

EXAMPLES = '''
# An example for editing of config parameters
- hosts: localhost
  connection: local
  tasks:
    - name: edit config parameters
      lxd_config:
        config:
          core.https_address: 192.168.0.1:8443

# An example for editing config parameters via network
- hosts: localhost
  connection: local
  tasks:
  - name: edit config parameters via network
    lxd_config:
      url: https://127.0.0.1:8443
      # These client_cert and client_key values are equal to the default values.
      #client_cert: "{{ lookup('env', 'HOME') }}/.config/lxc/client.crt"
      #client_key: "{{ lookup('env', 'HOME') }}/.config/lxc/client.key"
      trust_password: mypassword
      name: lxdbr0
      state: present
      config:
        bridge.driver: openvswitch
        ipv4.address: 10.0.3.1/24
        ipv6.address: fd1:6997:4939:495d::1/64
      description: My network
'''

RETURN = '''
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

# CONFIG_PARAMS is a list of config attribute names.
CONFIG_PARAMS = [
    'config'
]

# CONFIG_DEFAULTS is the default config deployed.
CONFIG_DEFAULTS = {}


class LXDConfig(object):
    def __init__(self, module):
        """Management of LXC containers via Ansible.

        :param module: Processed Ansible Module.
        :type module: ``object``
        """
        self.module = module
        self.cert_file = self.module.params.get('client_cert', None)
        self.key_file = self.module.params.get('client_key', None)
        self._build_config()
        self.trust_password = self.module.params.get('trust_password', None)
        self.url = self.module.params['url']
        self.debug = self.module._verbosity >= 4
        try:
            self.client = LXDClient(
                self.url, key_file=self.key_file, cert_file=self.cert_file,
                debug=self.debug
            )
        except LXDClientException as e:
            self.module.fail_json(msg=e.msg)
        self.actions = []

    def _build_config(self):
        self.config = {}
        for attr in CONFIG_PARAMS:
            param_val = self.module.params.get(attr, None)
            if attr == 'config':
                if param_val is None:
                    param_val = {}
                CONFIG_DEFAULTS.update(param_val)
                param_val = CONFIG_DEFAULTS
            if param_val is not None:
                self.config[attr] = param_val

    def _get_config_json(self):
        return self.client.do(
            'GET', '/1.0'.format(self),
            ok_error_codes=[404]
        )

    def _update_config(self):
        if self._needs_to_apply_config_configs():
            self._apply_config_configs()

    def _needs_to_change_config_config(self, key):
        if key not in self.config:
            return False
        old_configs = self.old_config_json['metadata'].get(key, None)
        return self.config[key] != old_configs

    def _needs_to_apply_config_configs(self):
        return (
            self._needs_to_change_config_config('config')
        )

    def _apply_config_configs(self):
        config = self.old_config_json.copy()
        for k, v in self.config.items():
            config[k] = v
        self.client.do('PUT', '/1.0'.format(self), config)
        self.actions.append('apply_config_configs')

    def run(self):
        """Run the main method."""

        try:
            if self.trust_password is not None:
                self.client.authenticate(self.trust_password)

            self.old_config_json = self._get_config_json()

            self._update_config()

            state_changed = len(self.actions) > 0
            result_json = {
                'changed': state_changed,
                'actions': self.actions
            }
            if self.client.debug:
                result_json['logs'] = self.client.logs
            self.module.exit_json(**result_json)
        except LXDClientException as e:
            state_changed = len(self.actions) > 0
            fail_params = {
                'msg': e.msg,
                'changed': state_changed,
                'actions': self.actions
            }
            if self.client.debug:
                fail_params['logs'] = e.kwargs['logs']
            self.module.fail_json(**fail_params)


def main():
    """Ansible Main module."""

    module = AnsibleModule(
        argument_spec=dict(
            client_cert=dict(
                type='str',
                default='{}/.config/lxc/client.crt'.format(os.environ['HOME']),
                aliases=['cert_file']
            ),
            client_key=dict(
                type='str',
                default='{}/.config/lxc/client.key'.format(os.environ['HOME']),
                aliases=['key_file']
            ),
            config=dict(
                type='dict',
            ),
            trust_password=dict(
                type='str',
                no_log=True
            ),
            url=dict(
                type='str',
                default='unix:/var/lib/lxd/unix.socket'
            )
        ),
        supports_check_mode=True,
    )

    lxd_manage = LXDConfig(module=module)
    lxd_manage.run()


if __name__ == '__main__':
    main()

