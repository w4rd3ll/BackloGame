#!/bin/sh
set -eu
server_ip="${1:?IP address required}"
case "$server_ip" in *[!0-9.]*|'') exit 2;; esac
staging=/opt/backlogame-staging
test -d "$staging"
test ! -e /etc/systemd/system/backlogame-steam.service
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-upgrade --no-install-recommends nginx python3-venv
install -d -m 755 /opt/backlogame /etc/backlogame /var/lib/backlogame-acme
install -m 644 "$staging/relay.py" "$staging/library_sync.py" /opt/backlogame/
install -m 600 /dev/null /etc/backlogame/steam-api-key
install -m 700 "$staging/set-steam-key.py" /usr/local/sbin/backlogame-set-steam-key
install -m 644 "$staging/backlogame-steam.service" /etc/systemd/system/
sed "s/__SERVER_IP__/$server_ip/g" "$staging/nginx-http.conf" >/etc/nginx/sites-available/backlogame-http
ln -s /etc/nginx/sites-available/backlogame-http /etc/nginx/sites-enabled/backlogame-http
if test -L /etc/nginx/sites-enabled/default && test "$(readlink /etc/nginx/sites-enabled/default)" = /etc/nginx/sites-available/default; then
    unlink /etc/nginx/sites-enabled/default
fi
nginx -t
systemctl daemon-reload
systemctl enable --now backlogame-steam.service
systemctl reload nginx
python3 -m venv /opt/backlogame-certbot
/opt/backlogame-certbot/bin/python -m pip install 'certbot>=5.4,<6'
printf '#!/bin/sh\n/usr/sbin/nginx -t && /bin/systemctl reload nginx\n' >/usr/local/sbin/backlogame-reload-nginx
chmod 700 /usr/local/sbin/backlogame-reload-nginx
install -m 644 "$staging/backlogame-cert-renew.service" "$staging/backlogame-cert-renew.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl is-active backlogame-steam.service
/opt/backlogame-certbot/bin/certbot --version
curl --silent http://127.0.0.1:8787/health
# HTTPS issuance and public relay are deliberately not activated here. Obtain
# the operator's agreement to the CA terms and install their API key first.
