# Steam library relay

This optional service keeps the operator's Steam Web API key on their VPS. The
portable client sends only a public Steam profile identifier over HTTPS. It does
not handle Steam passwords, login cookies or private libraries.

The relay binds to loopback port 8787. Nginx exposes only `/health` and
`/v1/steam/library?profile=…` over verified HTTPS. The key is installed through
`/usr/local/sbin/backlogame-set-steam-key`, entered without echo, stored as a
root-owned file with mode 600, and passed to the service through systemd
credentials. Never commit a key or place it in the client.

Protection: ten-minute cache (32 profiles maximum), two simultaneous upstream
calls, 5000 upstream requests per UTC day per process, nginx limits of twelve
requests per minute per IP and three connections. The daily in-memory counter
resets after a service restart; nginx is the persistent front door. Request URLs
are not logged. The service runs as a dynamic unprivileged user with a 160 MiB
memory limit. It is not an arbitrary HTTP proxy.

Installation requires the operator's explicit authorization for package and
service changes and acceptance of the certificate authority's subscriber
agreement. `prepare-vps.sh` targets a fresh Ubuntu VPS configuration without an
existing nginx site and must not be blindly rerun on an existing deployment.
Review conflicts before uploading files or enabling services. The normal app
build does not package these deployment scripts or server credentials.

For HTTPS without a domain, Certbot 5.4+ can request a Let's Encrypt IP certificate
using webroot and `--preferred-profile shortlived --ip-address <VPS_IP>`.
Authorize the CA terms before issuance. The supplied systemd timer checks renewal
twice daily, and a successful renewal reloads nginx. Test it with `certbot renew
--dry-run --run-deploy-hooks --no-random-sleep-on-renew`.

After deployment and key entry, verify a real public library before considering
the integration complete. Enter the HTTPS origin in BackloGame Settings → Sources
→ Steam service URL. With that configured, a blank personal key uses the relay;
a supplied personal key goes directly to Steam. Update the relay's
`library_sync.py` together with the client-side provider code when necessary.

Operational checks: `systemctl status backlogame-steam`, `systemctl list-timers
backlogame-cert-renew.timer`, HTTPS `/health`, and `certbot certificates`.
Missing or invalid keys, a private profile, a quota limit or a Steam outage must
be reported without exposing credentials. HTTPS health alone does not validate
the Steam key.
