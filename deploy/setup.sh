#!/usr/bin/env bash
# First time setup on a fresh Ubuntu 24.04 server (Azure VM):
#   sudo bash setup.sh your-domain.me
# Then copy procurement.db, .env, .secret_key and farmer-ivr/private.key into
# /srv/krishi (see README) and run: systemctl restart krishi
set -euo pipefail

DOMAIN="${1:?usage: setup.sh <domain>}"
REPO=https://github.com/siddhulaheja-ctrl/farmer-procurement-platform.git
APP=/srv/krishi

# the app uses date.today() for slots, so the server has to be on IST
timedatectl set-timezone Asia/Kolkata

apt-get update
apt-get install -y python3-venv git caddy ufw

# 1 GB VM, a bit of swap so pip / gunicorn don't get OOM killed
if [ ! -f /swapfile ]; then
    fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
    echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

id krishi >/dev/null 2>&1 || useradd --system --create-home --home-dir /home/krishi --shell /usr/sbin/nologin krishi
if [ ! -d "$APP/.git" ]; then
    git clone "$REPO" "$APP"
fi
mkdir -p "$APP/farmer-ivr"
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --quiet -r "$APP/requirements.txt"
chown -R krishi:krishi "$APP"

cat > /etc/systemd/system/krishi.service <<UNIT
[Unit]
Description=Krishi Sutra
After=network.target

[Service]
User=krishi
WorkingDirectory=$APP
ExecStart=$APP/venv/bin/gunicorn app:app --bind 127.0.0.1:8000 --workers 2 --timeout 60
Restart=always

[Install]
WantedBy=multi-user.target
UNIT

# caddy gets the https certificate by itself
cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN, www.$DOMAIN {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
CADDY

ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable

bash "$APP/deploy/backup.sh"

systemctl daemon-reload
systemctl enable krishi
systemctl reload caddy || systemctl restart caddy
echo "done. copy the database and secrets over, then: systemctl restart krishi"
