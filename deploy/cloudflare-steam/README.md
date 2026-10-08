# Steam service on Cloudflare Workers

Prepared for Workers Free; no custom domain or VPS is required. This is an
alternative to the VPS relay, not a proxy to its IP (Workers fetch cannot use
literal IP addresses). The included desktop configuration uses a deployed workers.dev origin.
Self-hosting this Worker is optional; no VPS is required for the shared service.

Deploy with official Wrangler 4.36.0 or newer, using the included
`wrangler.jsonc`, which also configures the rate-limit binding.
Do not upgrade to Workers Paid.

From this directory:

```sh
npm exec --yes --package=wrangler -- wrangler login --scopes account:read user:read workers:write workers_scripts:write workers_routes:write
npm exec --yes --package=wrangler -- wrangler deploy
```

The owner reviews and authorizes the OAuth permissions. OAuth background
access is included by Wrangler; revoke access from Cloudflare Connected
Applications when it is no longer needed.
Set `STEAM_API_KEY` as a Secret in the dashboard. The owner enters the key
directly; do not commit it, print it, or include it in deployment configuration.

Bind a rate limiter named `LIBRARY_RATE_LIMIT`, with 12 requests per 60 seconds
per key. The Worker refuses library requests without this binding. Disable
Worker invocation logs to avoid unnecessarily retaining profile queries.

The only public routes are GET `/health` and GET
`/v1/steam/library?profile=<SteamID64 or vanity name or public profile URL>`.
Only two fixed official Steam API endpoints can be called. Responses contain
App IDs and titles, never the key or upstream URLs. Results may be cached at
each Cloudflare location for five minutes. Rate limits are local to Cloudflare
locations, not a strict global Steam daily quota.

Before switching BackloGame: verify the live health route, public library,
private-profile errors, request limits and compatibility with the desktop
client. Configure the actual workers.dev origin only after those checks.
Do not remove the app's existing service setting until migration is verified.

Workers Free has 100,000 incoming requests/day and 10 ms CPU time per request;
network wait does not count as CPU time. Verify actual large-library CPU usage
before announcing support. Reaching a Free limit fails requests; do not enable
Paid billing to work around it without the owner's authorization.

Official references:
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/workers/platform/known-issues/
# IGDB catalog

The same Worker serves fixed read-only IGDB routes:

- `GET /v1/igdb/search?q=title`
- `GET /v1/igdb/game?id=123`

Store `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET` as Worker Secrets. Never put
credentials in Wrangler configuration, desktop settings, release binaries or logs.
The Worker obtains and refreshes a Twitch client-credentials access token itself.
It returns only normalized public game metadata, series and image URLs.

An independent rate limiter allows 60 requests per minute per IP. Results are
cached for 30 minutes and upstream queries are spaced in each Worker isolate.
Only the games endpoint and a fixed set of fields are queried; callers cannot
supply APICalypse, an upstream URL, headers or an access token.

IGDB API documentation: https://api-docs.igdb.com/
