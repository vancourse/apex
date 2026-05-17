# Security — TypeScript / React-specific patterns

Browser + Node-specific security rules. Methodology and broader patterns live in `apex:security-review`. Auth-flow / threat-model design lives in `apex:threat-model`.

## Never Put Secrets in `localStorage` or `sessionStorage`

**Rule:** Bearer tokens, API keys, refresh tokens, OAuth access tokens — none of these live in `localStorage` / `sessionStorage`. Use `httpOnly` + `Secure` + `SameSite=Strict` cookies.
**Why:** Any XSS = full token exfiltration. `localStorage` is JavaScript-accessible by definition; the moment a script you don't control runs in the page (XSS, malicious npm dep, compromised CDN), the token is gone. `httpOnly` cookies aren't accessible to JS at all.

```typescript
// ❌ BAD: token in localStorage
localStorage.setItem('authToken', token);
fetch('/api/data', { headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` } });

// ✅ GOOD: token in httpOnly cookie (server sets it on login response)
// Set-Cookie: auth=<token>; HttpOnly; Secure; SameSite=Strict; Path=/
fetch('/api/data', { credentials: 'include' });  // cookie sent automatically
```

If you MUST store something on the client (genuinely public state, last-route, theme preference), `localStorage` is fine — just not for credentials.

## XSS: Avoid `dangerouslySetInnerHTML` / `v-html` / Direct DOM Mutation

**Rule:** React's default JSX rendering escapes. Use it. Reject `dangerouslySetInnerHTML` unless the input is provably safe (came from your own server, sanitized via DOMPurify with a strict allowlist, AND there's a comment explaining the justification).
**Why:** XSS is still the #1 web vulnerability. React's `dangerouslySetInnerHTML` is the explicit XSS opt-in; reviewers should treat it as code-review-blocking unless justified.

```typescript
// ❌ BAD: user-supplied HTML rendered raw
<div dangerouslySetInnerHTML={{ __html: userComment }} />

// ✅ GOOD: let React escape
<div>{userComment}</div>

// ✅ ACCEPTABLE: sanitized + justified
// userComment is plain text but contains markdown links we want to render;
// sanitized via DOMPurify with ALLOWED_TAGS=['a', 'b', 'i', 'p']
<div dangerouslySetInnerHTML={{ __html: sanitize(userComment) }} />
```

## CSRF: SameSite Cookies + Anti-CSRF Tokens for State-Changing Endpoints

**Rule:** Session cookies use `SameSite=Strict` (or `Lax` with explicit justification). State-changing endpoints (POST / PUT / PATCH / DELETE) also accept an anti-CSRF token (double-submit cookie, synchronizer token, or framework-provided).
**Why:** `SameSite=Strict` blocks the canonical CSRF attack (attacker site triggers cross-origin request). Anti-CSRF tokens defend against the residual cases (e.g., subdomain attacks, browser bugs, header-injection variants).

## CSP: Strict Content-Security-Policy Header

**Rule:** Set `Content-Security-Policy` on every HTML response. At minimum: `default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'`. No `unsafe-inline` for scripts.
**Why:** CSP is the last line of defense against XSS. A strict CSP blocks injected scripts even if `dangerouslySetInnerHTML` is misused.

Use a nonce-based CSP for inline scripts you genuinely need:

```typescript
// Server generates per-response nonce
res.setHeader('Content-Security-Policy', `default-src 'self'; script-src 'self' 'nonce-${nonce}'`);

// Template includes nonce on the script tag
<script nonce={nonce}>/* ... */</script>
```

## Cookie Flags: `HttpOnly` + `Secure` + `SameSite`

**Rule:** Every session / auth cookie sets all three:

- `HttpOnly` — not accessible to JS
- `Secure` — HTTPS only (rejects on plaintext HTTP)
- `SameSite=Strict` or `SameSite=Lax` (with rationale for `Lax`)

```typescript
// ✅ GOOD: framework helper sets all three
res.cookie('session', token, {
  httpOnly: true,
  secure: true,
  sameSite: 'strict',
  maxAge: 24 * 60 * 60 * 1000,
});
```

## URL Redirect: Validate the Target Before Redirecting

**Rule:** Any `?next=` / `?returnTo=` / `?redirect=` query parameter must be validated against an allowlist (relative paths only, OR specific full URLs you control) before being used as a redirect target.
**Why:** Open redirects are used in phishing campaigns (your domain → attacker domain via your trusted redirect endpoint) and as part of OAuth-flow attacks.

```typescript
// ❌ BAD: open redirect
window.location.href = new URLSearchParams(location.search).get('next');

// ✅ GOOD: validate
const next = new URLSearchParams(location.search).get('next');
const safeRelative = next?.startsWith('/') && !next.startsWith('//') ? next : '/';
window.location.href = safeRelative;
```

## `postMessage`: Always Check `origin`

**Rule:** When receiving a `postMessage`, ALWAYS verify `event.origin` matches your expected origin. Never trust the message contents without origin verification.
**Why:** Any iframe / window in the browser can call `postMessage` on your window. Without origin check, you're accepting messages from any site.

```typescript
// ❌ BAD: no origin check
window.addEventListener('message', (event) => {
  if (event.data.type === 'auth-success') {
    setToken(event.data.token);  // attacker can spoof
  }
});

// ✅ GOOD: origin allowlist
const TRUSTED_ORIGINS = ['https://auth.example.com'];
window.addEventListener('message', (event) => {
  if (!TRUSTED_ORIGINS.includes(event.origin)) return;
  if (event.data.type === 'auth-success') {
    setToken(event.data.token);
  }
});
```

## iframe Sandboxing

**Rule:** Any iframe loading user-supplied content (or third-party content) sets `sandbox="..."` with the minimum capabilities needed. Default to no allowlist; add only what's required.
**Why:** `sandbox` is a structural defense — even if the iframe content is malicious, the sandbox limits what it can do.

```html
<!-- ❌ BAD: iframe with no sandbox -->
<iframe src={userSuppliedUrl} />

<!-- ✅ GOOD: minimal sandbox -->
<iframe src={userSuppliedUrl} sandbox="allow-scripts" referrerPolicy="no-referrer" />
```

## Sanitize User-Supplied URLs Before Rendering

**Rule:** Before rendering a user-supplied URL as a clickable link (`<a href={...}>`) or as the `src` of an image / iframe, validate it starts with an allowed protocol (`http:`, `https:`, `mailto:` — and explicitly NOT `javascript:` or `data:`).
**Why:** `javascript:` URLs execute on click. `data:` URLs can carry arbitrary content. Both are XSS vectors that bypass React's default escaping (it escapes `<` / `>`, not the URL protocol).

```typescript
function sanitizeUrl(url: string): string {
  try {
    const parsed = new URL(url, window.location.origin);
    if (['http:', 'https:', 'mailto:'].includes(parsed.protocol)) return url;
  } catch {}
  return '#';  // fail-closed
}

<a href={sanitizeUrl(userSuppliedUrl)}>link</a>
```

## Subresource Integrity (SRI) for External Scripts / Styles

**Rule:** Any `<script>` or `<link>` loaded from a third-party CDN includes an `integrity="sha384-..."` attribute matching the file's hash.
**Why:** SRI guards against CDN compromise. If the CDN serves modified content, the browser refuses to execute it.

```html
<script
  src="https://cdn.example.com/lib.js"
  integrity="sha384-AbCdEfG..."
  crossOrigin="anonymous"
></script>
```

Prefer bundling third-party code yourself when feasible; SRI is the fallback when you can't.

## Don't Log Secrets in Console or Reach Sentry / Error Tracker

**Rule:** Configure your error tracker (Sentry, Bugsnag, Datadog RUM) with a `beforeSend` filter that strips authorization headers, cookies, query params named `token` / `secret` / `key`, and any localStorage key matching a sensitivity heuristic.
**Why:** Frontend error trackers capture more than you think — full request URLs (including tokens in query strings), localStorage state, network bodies. Without filtering, your error tracker becomes a secret aggregator.

## Cross-References

For the methodology this file implements (threat model, audit log, dependency vuln scanning), see `apex:security-review`. For server-side / backend security patterns, see `apex:python-review/rules/security.md`.
