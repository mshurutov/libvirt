#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2016, Sofiane Medjkoune <sofiane@medjkoune.fr> based on lxd_profile by Hiroaki Nakamura <hnakamur@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: lxd_storage
short_description: Manage LXD storage pools
version_added: "2.15"
description:
  - Management of LXD storage pools
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
          - 'The config for the storage pool (e.g.
            {
                "lvm.thinpool_name": "lxdltp",
                "lvm.vg.force_reuse": "yes",
                "lvm.vg_name": "vg",
                source": "vg"
            } for LVM thin pool based storage).
            See U(https://github.com/lxc/lxd/blob/master/doc/rest-api.md#post-11)'
          - If the storage pool already exists and its "config" value in metadata
            obtained from
            GET /1.0/storage-pools/<name>
            U(https://github.com/lxc/lxd/blob/master/doc/rest-api.md#get-16)
            are different, then this module tries to apply the configurations.
        required: false
    description:
        description:
          - Description of a storage.
        required: false
    driver:
        description:
          - LXD store images, instances and custom volumes on storage pool.
            Every storage pool should use one of follow drivers:
            - 'Btrfs - btrfs'
            - 'CephFS - cephfs'
            - 'Ceph Object - cephobject'
            - 'Ceph RBD - ceph'
            - 'Directory - dir'
            - 'LVM - lvm'
            - 'ZFS - zfs'
        required: true
    name:
        description:
          - Name of storage pool.
        required: true
    state:
        choices:
          - present
          - absent
        description:
          - Define the state of a storage pool.
        required: false
        default: present
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
  - Storage pool must have a unique name. If you attempt to create a
    storage pool with a name that already existed in the users namespace
    the module will simply return as "unchanged".
'''

EXAMPLES = '''
# An example for creating a storage pools
- hosts: localhost
  connection: local
  tasks:
    - name: Create a storage pools
      lxd_storage:
        name: lvm
        driver: lvm
        state: present
        config:
          lvm.thinpool_name: lxdltp
          lvm.vg.force_reuse: yes
          lvm.vg_name: vg
          source: vg
        description: LVM storage pool

# An example for creating a storage pool via https connection
- hosts: localhost
  connection: local
  tasks:
  - name: create dir storage via remote connection
    lxd_storage:
      url: https://127.0.0.1:8443
      # These client_cert and client_key values are equal to the default values.
      #client_cert: "{{ lookup('env', 'HOME') }}/.config/lxc/client.crt"
      #client_key: "{{ lookup('env', 'HOME') }}/.config/lxc/client.key"
      trust_password: mypassword
      name: dir_pool
      driver: dir
      state: present
      config:
        source: /opt/lxd/pools/dir_pool
      description: My directory storage pool

# An example for deleting a btrfs storage pool
- hosts: localhost
  connection: local
  tasks:
    - name: Delete a storage pool
      lxd_storage:
        name: lxdbtrfs
        state: absent
'''

RETURN = '''
old_state:
  description: The old state of the storage pool
  returned: success
  type: string
  sample: "absent"
logs:
  description: The logs of requests and responses.
  returned: when ansible-playbook is invoked with -vvvv.
  type: list
  sample: "(too long to be placed here)"
actions:
  description: List of actions performed for the storage pool.
  returned: success
  type: list
  sample: '["create"]'
'''

import os

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.lxd import LXDClient, LXDClientException


# STORAGES_STATES is a list for states supported.
STORAGES_STATES = [
    'present', 'absent'
]

# STORAGES_CONFIG_PARAMS is a list of config attribute names.
STORAGES_CONFIG_PARAMS = [
    'config', 'description', 'driver'
]

# STORAGES_CONFIG_DEFAULTS is the default config deployed.
STORAGES_CONFIG_DEFAULTS = {}


class LXDStorageManagement(object):
    def __init__(self, module):
        """Management of LXC containers via Ansible.

        :param module: Processed Ansible Module.
        :type module: ``object``
        """
        self.module = module
        self.cert_file = self.module.params.get('client_cert', None)
        self.key_file = self.module.params.get('client_key', None)
        self._build_config()
        self.driver = self.module.params['driver']
        self.name = self.module.params['name']
        self.state = self.module.params['state']
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
        for attr in STORAGES_CONFIG_PARAMS:
            param_val = self.module.params.get(attr, None)
            if attr == 'config':
                if param_val is None:
                    param_val = {}
                STORAGES_CONFIG_DEFAULTS.update(param_val)
                param_val = STORAGES_CONFIG_DEFAULTS
            if param_val is not None:
                self.config[attr] = param_val

    def _get_storage_json(self):
        return self.client.do(
            'GET', '/1.0/storage-pools/{0}'.format(self.name),
            ok_error_codes=[404]
        )

    @staticmethod
    def _storage_json_to_module_state(resp_json):
        if resp_json['type'] == 'error':
            return 'absent'
        return 'present'

    def _update_storage(self):
        if self.state == 'present':
            if self.old_state == 'absent':
                self._create_storage()
            else:
                if self._needs_to_apply_storage_configs():
                    self._apply_storage_configs()
        elif self.state == 'absent':
            if self.old_state == 'present':
                self._delete_storage()

    def _create_storage(self):
        config = self.config.copy()
        config['name'] = self.name
        self.client.do('POST', '/1.0/storage-pools', config)
        self.actions.append('create')

    def _needs_to_change_storage_config(self, key):
        if key not in self.config:
            return False
        old_configs = self.old_storage_json['metadata'].get(key, None)
        return self.config[key] != old_configs

    def _needs_to_apply_storage_configs(self):
        return (
            self._needs_to_change_storage_config('config') or
            self._needs_to_change_storage_config('description')
        )

    def _apply_storage_configs(self):
        config = self.old_storage_json.copy()
        for k, v in self.config.items():
            config[k] = v
        self.client.do('PUT', '/1.0/storage-pools/{}'.format(self.name), config)
        self.actions.append('apply_storage_configs')

    def _delete_storage(self):
        self.client.do('DELETE', '/1.0/storage-pools/{}'.format(self.name))
        self.actions.append('delete')

    def run(self):
        """Run the main method."""

        try:
            if self.trust_password is not None:
                self.client.authenticate(self.trust_password)

            self.old_storage_json = self._get_storage_json()

            self.old_state = self._storage_json_to_module_state(self.old_storage_json)
            self._update_storage()

            state_changed = len(self.actions) > 0
            result_json = {
                'changed': state_changed,
                'old_state': self.old_state,
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
            description=dict(
                type='str',
            ),
            driver=dict(
                type='str',
                required=True
            ),
            name=dict(
                type='str',
                required=True
            ),
            state=dict(
                choices=STORAGES_STATES,
                default='present'
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

    lxd_manage = LXDStorageManagement(module=module)
    lxd_manage.run()


if __name__ == '__main__':
    main()

