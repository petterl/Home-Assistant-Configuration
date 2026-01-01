#!/bin/bash
export GIT_SSH_COMMAND="ssh -i /config/.ssh/id_ed25519 -o UserKnownHostsFile=/config/.ssh/known_hosts -o StrictHostKeyChecking=no"
cd /config
git fetch origin
git reset --hard origin/master
