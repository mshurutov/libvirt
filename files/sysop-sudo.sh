#!/bin/bash
# wrapper for enable wheel group in /etc/sudoers by script

sed -ie 's/^.*\(%wheel.*NOPASSWD.*\)$/\1/'
