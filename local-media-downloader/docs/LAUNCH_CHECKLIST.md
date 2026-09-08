# Loady launch checklist

This checklist supplements `DEPLOYMENT.md`. Never paste secret values into commands, tickets, or logs.

## Blockers before public launch

- Rotate the Resend API key that appeared in a screenshot, update the VPS secret out of band, and send one verification and one password-reset message to an owned test address.
- Complete Paddle Live approval. Create Live products/prices independently of Sandbox; set the Live API key, client token, webhook secret, and four Live price IDs only during an approved maintenance window. Subscribe the webhook to transaction and subscription lifecycle events used by the application, approve `loady.cc` if Paddle requires it, then run a low-value real-payment/refund test with an authorized card.
- Publish a monitored support/contact channel and replace the generic support-channel wording in the legal pages. Have the Terms, Privacy, Copyright, Acceptable Use, and Billing/Refund policies reviewed for the operator's jurisdiction. Add genuine business identity details only when known.
- Promote the intended administrator using the documented server-side script after verifying the email address: `docker compose --env-file .env.production -f compose.production.yml exec backend python -m app.scripts.promote_admin administrator@example.com`. Do not grant admin through frontend state or direct browser requests.
- Audit the IPv6 firewall with administrator privileges (commands below). Preserve SSH before changing any rule.

## High priority

- Configure an independent uptime check for `https://loady.cc/` and `/api/health`; alert on repeated failures, certificate expiry, container restarts, disk usage above 75%, and backup failures.
- Run `scripts/restore-rehearsal.sh` against the newest PostgreSQL and SQLite backups monthly and after backup-script changes.
- Add encrypted off-server copies of PostgreSQL, SQLite, and production configuration. Never back up downloaded media or temporary files.
- Review Content-Security-Policy reports during real Sandbox checkout and representative preview/download flows. Enforce only after required Paddle/CDN origins are confirmed.

## Firewall verification

The Cloudflare jump must apply only to packets arriving on the public interface. An unqualified destination-port jump can also catch container egress replies and block outbound HTTPS.

```sh
sudo iptables -S DOCKER-USER
sudo iptables -S LOADY-CLOUDFLARE
sudo ip6tables -S DOCKER-USER
sudo ip6tables -S LOADY-CLOUDFLARE
sudo ufw status verbose
sudo grep -R "LOADY-CLOUDFLARE" /etc/iptables /etc/ufw /etc/systemd /usr/local/sbin 2>/dev/null
```

Expected IPv4 and, when Docker publishes IPv6, IPv6 jump shape:

```sh
-A DOCKER-USER -i eth0 -p tcp -m multiport --dports 80,443 -j LOADY-CLOUDFLARE
```

If IPv6 contains the old unqualified jump, first record `ip6tables-save`, verify the public interface name, insert the interface-qualified replacement before deleting only the exact old rule, test SSH in a second session, test container outbound HTTPS, then persist with `sudo netfilter-persistent save`. Do not copy commands blindly when the interface or rule order differs.

Verify no public bindings for backend, PostgreSQL, or Docker API:

```sh
docker compose --env-file .env.production -f compose.production.yml ps
sudo ss -lntp | grep -E ':(8000|5432|2375|2376)\b' && echo "UNEXPECTED LISTENER" || true
docker compose --env-file .env.production -f compose.production.yml exec backend python -c "import urllib.request; print(urllib.request.urlopen('https://sandbox-api.paddle.com', timeout=10).status)"
```

Also probe TikTok, Resend, and Paddle connectivity without printing credentials. A 401/403 from an unauthenticated API probe still demonstrates outbound TLS connectivity.

## Cloudflare manual checklist

- SSL/TLS mode Full (strict); valid origin certificate installed; Always Use HTTPS enabled.
- Apex and `www` proxied; one reviewed redirect from `www` to apex.
- Origin 80/443 restricted to current official Cloudflare ranges; update the maintained allowlist when Cloudflare changes it.
- Do not cache `/api/*`, authenticated HTML, or checkout responses. Cache fingerprinted `/assets/*` aggressively.
- Enable managed protections conservatively and verify signup, checkout, SSE, downloads, TikTok analysis, and webhook delivery. Do not enable a bot challenge that intercepts API/SSE/webhook traffic.

## Search Console follow-up

- Recheck `https://loady.cc/sitemap.xml`, submitted/last-read status, and all eight canonical SEO URLs.
- Review indexed pages, Google-selected canonical, mobile usability, Core Web Vitals, structured-data errors, and crawl/404 reports weekly through launch month.
- Do not infer indexing from a successful HTTP response; use Search Console's URL inspection.

## Operations and capacity

- Keep one Uvicorn worker and `LMD_MAX_CONCURRENT_DOWNLOADS=1` on the 4-vCPU/8-GB beta VPS.
- Alert before the disposable-media volume approaches its 40-GiB ceiling. Confirm cleanup runs hourly, authenticated media expires around 24h, guest media around 48h, and partials around 6h.
- Run `BASE_URL=https://loady.cc scripts/production-smoke.sh` after deployment. Live third-party media probes are manual/optional; deterministic CI tests remain mocked.

## Post-launch

- Review 429 and 5xx frequency, queue latency, failed jobs, FFmpeg duration, disk growth, Paddle webhook failures, email delivery, and subscription reconciliation.
- Reassess rate limits from real traffic before adding multiple backend workers; the current limiter is intentionally process-local.

## Optional

- Add a privacy-conscious analytics provider only after consent/legal review. Never record media URLs, titles, emails, IPs, tokens, or payment data. Existing event scaffolding contains event names and coarse plan values only.
- Add paid monitoring or backup services later; neither is required to validate the initial architecture.
