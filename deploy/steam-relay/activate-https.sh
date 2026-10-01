#!/bin/sh
set -eu
server_ip="${1:?IP address required}"
case "$server_ip" in *[!0-9.]*|'') exit 2;; esac
test -f "/etc/letsencrypt/live/$server_ip/fullchain.pem"
test ! -e /etc/nginx/sites-enabled/backlogame-https
sed "s/__SERVER_IP__/$server_ip/g" /opt/backlogame-staging/nginx-https.conf >/etc/nginx/sites-available/backlogame-https
ln -s /etc/nginx/sites-available/backlogame-https /etc/nginx/sites-enabled/backlogame-https
nginx -t
systemctl reload nginx
systemctl enable --now backlogame-cert-renew.timer
systemctl is-active nginx backlogame-steam.service backlogame-cert-renew.timer
/opt/backlogame-certbot/bin/certbot renew --dry-run --run-deploy-hooks --no-random-sleep-on-renew
