#!/usr/bin/env bash
# pull the latest code on the server and restart: sudo bash update.sh
set -euo pipefail
cd /srv/krishi
sudo -u krishi git pull --ff-only
sudo -u krishi venv/bin/pip install --quiet -r requirements.txt
systemctl restart krishi
systemctl --no-pager status krishi | head -5
