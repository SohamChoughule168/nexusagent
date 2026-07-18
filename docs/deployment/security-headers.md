# Security Headers

Edge security headers enforced by nginx and the backend (Milestone 7, Phase 6).
See `nginx/nginx.conf` (HTTP) and `nginx/tls.conf.example` (HTTPS) for the live
config, and `backend/app/core/middleware.py` for the backend-side copy.

---

## Header set

| Header | Value | Purpose |
|--------|-------|---------|
| `Content-Security-Policy` | `default-src 'self'; img-src 'self' data:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'` | Restricts resource loading to same-origin; blocks injection/eval from foreign sources. |
| `X-Content-Type-Options` | `nosniff` | Stops MIME sniffing. |
| `X-Frame-Options` | `SAMEORIGIN` | Prevents clickjacking from other origins (same-origin framing allowed). |
| `X-XSS-Protection` | `1; mode=block` | Legacy XSS auditor (defense-in-depth; CSP is primary). |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Limits referrer leakage on cross-origin navigation. |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` | Disables powerful features the app does not use. |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | **TLS config only** — forces HTTPS. |

---

## How it is applied

- **nginx is the authority.** The active `nginx.conf` (and `tls.conf.example`)
  set all of the above with `add_header ... always`. It also uses
  `proxy_hide_header` to strip the backend's copies so no duplicate headers
  reach the client.
- **Backend defense-in-depth.** `SecurityHeadersMiddleware` sets the same policy
  on every response. This matters when the backend is reached directly (e.g. the
  local compose publishes port 8000). Behind nginx, those copies are stripped
  and nginx's win — the policies are kept intentionally identical.

---

## Tightening (recommended follow-ups)

- **CSP `script-src`:** drop `'unsafe-inline'` / `'unsafe-eval'` once
  `next.config` supplies per-request nonces (Next.js supports this). The current
  values keep Next.js runtime compatibility.
- **`X-Frame-Options` → CSP `frame-ancestors`.** Once CSP is strict, `XFO` is
  redundant; keep both for legacy clients.
- **HSTS `preload`:** only submit to the preload list after confirming the
  domain will *always* serve HTTPS.

---

## Container / proxy hardening notes

- The backend container runs as non-root `appuser` (uid 1001) and, in
  `docker-compose.aws.yml`, with `read_only: true` + `tmpfs: /tmp`.
- `nginx` is the sole public entrypoint (ports 80/443); the backend and frontend
  are reachable only on the internal bridge network. See `production.md` §1.
- nginx's master process binds 80/443 and drops to the unprivileged `nginx`
  worker user; its capability set is managed by the upstream image, so compose
  does not drop nginx capabilities (dropping them would break privileged-port
  binding / privilege drop). The alternative — run nginx as a non-root user on a
  high port (e.g. 8080) and publish that — is a future option if you want
  `cap_drop: [ALL]` on nginx too.
