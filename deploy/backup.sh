#!/usr/bin/env bash
# installs a nightly database backup (02:30, kept 14 days in /var/backups/krishi).
# setup.sh runs this, or on its own: sudo bash backup.sh
set -euo pipefail

cat > /usr/local/bin/krishi-backup <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
DIR=/var/backups/krishi
OUT="$DIR/procurement-$(date +%F).db"
mkdir -p "$DIR" && chmod 700 "$DIR"
# sqlite's backup api, safe while the app is writing
python3 -c "import sqlite3,sys; s=sqlite3.connect('file:/srv/krishi/procurement.db?mode=ro', uri=True); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close()" "$OUT"
gzip -f "$OUT"
find "$DIR" -name 'procurement-*.db.gz' -mtime +14 -delete
SCRIPT
chmod 755 /usr/local/bin/krishi-backup

cat > /etc/systemd/system/krishi-backup.service <<'UNIT'
[Unit]
Description=Krishi Sutra database backup

[Service]
Type=oneshot
ExecStart=/usr/local/bin/krishi-backup
UNIT

cat > /etc/systemd/system/krishi-backup.timer <<'UNIT'
[Unit]
Description=Nightly Krishi Sutra database backup

[Timer]
OnCalendar=*-*-* 02:30
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now krishi-backup.timer
