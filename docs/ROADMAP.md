# Packaging roadmap

This roadmap covers how SabzBank gets from a responsive web app to installable apps: a PWA first, then the collector and partner screens as PWA routes, then an Android package (APK or AAB through a Trusted Web Activity or Capacitor), then an iOS package (IPA through Capacitor). For each step it lists the prerequisites, the store requirements to check, the risks (clipboard and storage behaviour, the nonce CSP, deep links, push) and the order of work. There are no dates; each step starts when the previous one's exit condition holds. The product reasoning (the PWA is the planned channel, and a citizen APK does not unlock the pilot while the collector and partner screens do) comes from the product-owner review in [ROLE_REVIEWS.md](ROLE_REVIEWS.md).

## Order of work

| Step | What | Starts when | Exit condition |
|---|---|---|---|
| 1 | PWA: manifest, icons, service worker, offline page, install prompt | TLS is in front of the edge | Installable on Android Chrome and iOS Safari; offline launch shows the offline page, never a blank screen |
| 2 | Collector screen (`/collector`) as a PWA route | Phase A (measured weights) is built | A collector completes a pickup with measured weights from a phone |
| 3 | Partner screen (`/partner`) as a PWA route | Phase C (per-partner credentials) is built | A cashier spends a code by paste or scan |
| 4 | Android package | A measured trigger fires (for example, PWA installs or message reach below target), and the founder confirms the distribution channel | Signed package accepted by the chosen store |
| 5 | iOS package | A measured need the PWA cannot meet, and an Apple developer account | Accepted by App Store review, or distributed by the route the founder chooses |

Steps 2 and 3 can run in parallel once their backend phase lands.

## Step 1: PWA

### What exists

- `frontend/lib/api.ts` already does stale-while-revalidate for GETs, in memory: a page visited before renders its cached data at once and revalidates; a failed revalidation keeps the cached data on screen; every mutation calls `refresh()`, which clears the cache and refetches. This cache lives in the tab and dies with it.
- `frontend/app/icon.svg` is the only icon. `frontend/public/` has no tracked files.
- The CSP is set per request by `frontend/proxy.ts`, with a fresh nonce on every page response.
- The backend sends `cache-control: no-store` on every API response.

### Work

1. **Manifest** (`app/manifest.ts` or a static `manifest.webmanifest`): Persian `name` and `short_name` (سبزبانک), `dir: "rtl"`, `lang: "fa"`, `start_url: "/"`, `display: "standalone"`, theme and background colours for both themes, and the icons below.
2. **Icons**: 192 and 512 px PNG, a maskable variant, and an Apple touch icon (iOS ignores manifest icons for the home screen).
3. **Service worker** (`public/sw.js`, registered from the client shell):
   - Precache the offline page and its assets.
   - Cache-first for `/_next/static/*` (content-hashed, immutable).
   - Network-first for navigations, falling back to the offline page when the network fails. Do not serve cached HTML pages as the normal path (see "CSP" below).
   - Never cache `/api/*`. The in-memory cache in `api.ts` stays the only data cache. If an offline data view is wanted later, it must be per user and cleared on logout (phase B).
   - No offline write queue: redeem and complete are not idempotent, and replaying them could double-spend. Writes need the network.
   - Versioned cache names, old caches deleted on `activate`, and an update prompt instead of a silent `skipWaiting` mid-session.
4. **Offline page**: a static, localized page («ارتباط با سرور برقرار نشد» and «تلاش دوباره» are already in the copy), with no inline script, so it needs no nonce.
5. **Install prompt**: capture `beforeinstallprompt` on Android and show an install button after a meaningful action (a first completed pickup), not on first load. On iOS, show the Share then "Add to Home Screen" hint, because iOS has no install event.

### CSP and the service worker

- Add `worker-src 'self'` and `manifest-src 'self'` to the CSP in `proxy.ts`, so the worker and manifest are explicitly allowed rather than relying on fallback rules. `script-src` with `'strict-dynamic'` makes browsers that support it ignore `'self'` for scripts, so do not rely on `script-src` to cover the worker.
- The service worker script is fetched by the browser directly, not by a nonced `<script>`; it must be same-origin and served with the right content type.
- `/sw.js` passes through the `proxy.ts` matcher (only `api/`, `_next/static`, `_next/image`, `favicon.ico` and `icon.svg` are excluded) and receives the page CSP, which governs the worker's own fetches (`connect-src 'self'` is enough). Add it to the exclusions if that causes trouble.
- A cached HTML page carries the nonce it was rendered with, and the CSP header cached with it names the same nonce. Serving it again reuses a nonce, which weakens the protection a nonce gives. That is why navigations are network-first with a static offline page, not cache-first.

### Risks

| Risk | Detail | Mitigation |
|---|---|---|
| Plain HTTP | Service workers and `navigator.clipboard` need a secure context (HTTPS or localhost); compose serves HTTP | TLS first; it is the step's start condition |
| Clipboard | Without a secure context `navigator.clipboard` is undefined. The Copy button falls back to selecting the text and `document.execCommand("copy")`, and says «کپی شد» only when a copy happened | Keep the fallback; test on HTTP and HTTPS |
| Storage eviction | The web app keeps a citizen's reward codes in `localStorage`. Browsers can clear it (private windows, storage pressure, user action); check WebKit's eviction rules for sites and for home-screen web apps | Move the list to the server with accounts (phase B); until then the copy says it is kept on this device only |
| Stale app shell | A cached shell can outlive a deploy | Versioned caches and an update prompt |
| iOS limits | No install event; web push only for home-screen web apps on recent iOS versions | Install hint; do not depend on push (SMS is the channel, phase D) |

## Steps 2 and 3: collector and partner screens

| | Collector screen | Partner screen |
|---|---|---|
| Needs | Phase A: `complete` with measured weights | Phase C: per-partner credentials and `used_by` |
| Route | `/collector` | `/partner` |
| Does | Lists today's scheduled pickups, enters measured kg per material, completes | Paste or scan a code, see the reward and its status, spend it |
| Credential | Per-collector sign-in, or the shared key typed in and kept in memory (never in the bundle or `localStorage`) | Per-partner sign-in or key, likewise |
| Extra | Works on a phone outdoors: large targets, offline-tolerant reading of the day's list (no offline completes) | Camera access for scanning needs a `Permissions-Policy` change (`camera=()` today) scoped to this route |

Risks: a key typed into a shared device; a camera permission on the whole origin; collectors working with poor coverage. The privileged routes should also be reachable only from the allowed networks (the edge allowlist in phase C).

## Step 4: Android

Two ways to package the same PWA:

| | Trusted Web Activity (TWA) | Capacitor |
|---|---|---|
| What it is | A thin Android app that opens the hosted PWA full-screen in the user's browser engine | A native shell with a WebView that loads bundled assets or a remote URL |
| Fits | The PWA as is; the same CSP, service worker and cookies | Native features (camera plugins, secure storage, native push) |
| CSP | Unchanged: the hosted site keeps its per-request nonce | Bundled mode means a static export, which loses the per-request nonce: the CSP has to move to hashes or a meta tag. Loading the hosted URL keeps the nonce |
| Deep links | Digital Asset Links: `/.well-known/assetlinks.json` with the signing-key fingerprint | App Links (the same `assetlinks.json`), plus a custom scheme if needed |
| Tooling | Bubblewrap or PWABuilder | Capacitor CLI and Android Studio |

Prerequisites: step 1 done; a stable HTTPS hostname; a signing key kept off developer laptops; the distribution channel confirmed by the founder (the product-owner review assumes Iranian Android stores such as Cafe Bazaar and Myket plus direct download, with Google Play not a practical path for an Iranian pilot).

Store requirements to check for the chosen store: developer account and identity verification; package format (APK or AAB) and signing scheme; minimum and target Android API levels; a privacy policy URL and the data-collection declaration (phone number, address); content rating; the store's rules on in-app rewards and vouchers.

Risks: `/.well-known/assetlinks.json` must be served exactly, which `frontend/public/` and the `proxy.ts` matcher must allow; push through Google's services may not be reliable for users in Iran, so do not build on it; WebView storage can be cleared by the OS; Android backups must exclude session tokens.

## Step 5: iOS

Capacitor is the only route of the two (iOS has no TWA).

Prerequisites: an Apple developer account (check availability for an Iran-based team), a Mac build machine, step 1 done, and a reason the PWA cannot meet (the product-owner review puts the IPA out of scope for the pilot).

Store requirements to check: App Store review guideline 4.2 (minimum functionality): an app that only wraps a website can be rejected, so the package needs native value (for example the camera scanner); privacy nutrition labels; account deletion inside the app once accounts exist; no external payment links if rewards ever involve purchases.

Risks: Universal Links need `/.well-known/apple-app-site-association` served as JSON without a redirect; WKWebView storage and cookie behaviour differ from Safari's; the bundled-versus-remote CSP question is the same as on Android; review times delay fixes, so keep business rules on the server.

## What does not change

- The backend contract: every packaged client calls the same `/api/*` through the edge.
- The security headers and the CSP stay server-side; packaged clients load the hosted origin where possible.
- No secrets in any bundle: collector and partner credentials are entered or issued at run time.
