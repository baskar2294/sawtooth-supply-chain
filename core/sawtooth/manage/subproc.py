# Copyright 2016 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------------
import json
import logging
import os
import subprocess
import sys

from sawtooth.manage.node import NodeController
from sawtooth.manage.utils import get_executable_script
from sawtooth.validator_config import get_validator_configuration

LOGGER = logging.getLogger(__name__)


class SubprocessNodeController(NodeController):
    def __init__(self, host_name='localhost', verbose=False):
        self._host_name = host_name
        self._verbose = verbose
        self._base_config = get_validator_configuration([], {})
        self._v0_cfg = {
            "InitialConnectivity": 0,
        }
        self._nodes = {}

    def _construct_start_command(self, node_args):
        host = self._host_name
        node_name = node_args.node_name
        http_port = node_args.http_port
        gossip_port = node_args.gossip_port
        cmd = get_executable_script('txnvalidator')
        if self._verbose is True:
            cmd += ['-vv']
        cmd += ['--node', node_name]
        cmd += ['--listen', "{}:{}/TCP http".format(host, http_port)]
        cmd += ['--listen', "{}:{}/UDP gossip".format(host, gossip_port)]
        for x in node_args.config_files:
            cmd += ['--config', x]
        if node_args.genesis:
            # Create and indicate special config file
            config_dir = self._base_config['ConfigDirectory']
            if node_args.currency_home is not None:
                config_dir = os.path.join(node_args.currency_home, 'etc')
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            config_file = '{}_bootstrap.json'.format(node_name)
            with open(os.path.join(config_dir, config_file), 'w') as f:
                f.write(json.dumps(self._v0_cfg, indent=4))
            cmd += ['--config', config_file]
        return cmd

    def _get_out_err(self, node_args):
        return [sys.stdout, sys.stderr]

    def is_running(self, node_name):
        '''
        Authority on whether a node is in fact running.  On discovering that a
        node no longer exists, it removes the node from _nodes.  We do this
        here rather than in stop/kill in order to allow stop/kill to be
        non-blocking.  Thus, our internal model of nodes (_nodes) will always
        be correct the next time someone checks.
        Args:
            node_name (str):
        Returns:
            ret_val (bool):
        '''
        ret_val = False
        handle = None
        try:
            handle = self._nodes[node_name]['Handle']
        except KeyError:
            pass
        if handle is not None:
            handle.poll()
            if handle.returncode is None:
                ret_val = True
        if ret_val is False:
            # process is authoritatively stopped; toss handle if it exists
            self._nodes.pop(node_name, None)
        return ret_val

    def _build_env(self, node_args):
        env = os.environ.copy()
        env['PYTHONPATH'] = os.pathsep.join(sys.path)
        if node_args.currency_home is not None:
            env['CURRENCYHOME'] = node_args.currency_home

        return env

    def create_genesis_block(self, node_args):
        '''
        Creates a key, then uses this key to author a genesis block.  The node
        corresponding to node_args must be initially available on the network
        in order to serve this genesis block.
        Args:
            node_args (NodeArguments):
        '''
        if self.is_running(node_args.node_name) is False:
            # Create key for initial validator
            cmd = get_executable_script('sawtooth')
            cmd += ['keygen', node_args.node_name]
            # ...sawtooth keygen does not assume validator's CURRENCYHOME
            key_dir = self._base_config['KeyDirectory']
            if node_args.currency_home is not None:
                key_dir = os.path.join(node_args.currency_home, 'keys')
            cmd += ['--key-dir', key_dir]
            if self._verbose is False:
                cmd += ['--quiet']
            proc = subprocess.Popen(cmd, env=self._build_env(node_args))
            proc.wait()
            # Create genesis block
            cmd = get_executable_script('sawtooth')
            cmd += ['admin', 'poet0-genesis']
            if self._verbose is True:
                cmd += ['-vv']
            cmd += ['--node', node_args.node_name]
            for x in node_args.config_files:
                cmd += ['--config', x]
            proc = subprocess.Popen(cmd, env=self._build_env(node_args))
            proc.wait()

    def start(self, node_args):
        '''
        Start a node if it is not already running.
        Args:
            node_args (NodeArguments):
        '''
        node_name = node_args.node_name
        if self.is_running(node_name) is False:
            cmd = self._construct_start_command(node_args)
            # Execute popen and store the process handle
            [out, err] = self._get_out_err(node_args)
            handle = subprocess.Popen(cmd, stdout=out, stderr=err,
                                      env=self._build_env(node_args))
            handle.poll()
            if handle.returncode is None:
                # process is known to be running; save handle
                self._nodes[node_name] = {"Handle": handle}

    def stop(self, node_name):
        '''
        Send a non-blocking termination request to a node if it appears to be
        running.  OSError is caught and logged because the process may die
        between is_running and our signal transmission attempt.
        Args:
            node_name (str):
        '''
        if self.is_running(node_name) is True:
            try:
                handle = self._nodes[node_name]['Handle']
                handle.terminate()
            except OSError as e:
                LOGGER.debug('%s.stop failed: %s', self.__class__.__name__,
                             str(e))

    def kill(self, node_name):
        '''
        Send a non-blocking kill (9) to a node if it appears to be running.
        OSError is caught and logged because the process may die between
        is_running and our signal transmission attempt.
        Args:
            node_name (str):
        '''
        if self.is_running(node_name) is True:
            try:
                handle = self._nodes[node_name]['Handle']
                handle.kill()
            except OSError as e:
                LOGGER.debug('%s.kill failed: %s', self.__class__.__name__,
                             str(e))

    def get_node_names(self):
        names = self._nodes.keys()
        return [x for x in names if self.is_running(x)]

    def get_ip(self, node_name):

        hostname = self._host_name
        return hostname
