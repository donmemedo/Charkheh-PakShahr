# QA plan

This plan says how SabzBank is tested: acceptance criteria per feature, the boundary values and where each is pinned, an automation pyramid sized for this project (what exists and what to add next), a manual regression checklist for every release, and how to run the smoke and screenshot scripts. Backend behaviour quoted here is checked against [backend/main.py](../backend/main.py) and [backend/test_api.py](../backend/test_api.py). Frontend behaviour is checked against `frontend/` and described in [UI_UX.md](UI_UX.md). Persian copy quoted here comes from `frontend/lib/i18n.tsx` and follows the Persian UX-writing vocabulary.

## Acceptance criteria

### Pickup request

1. The form offers the five materials, a day, one of four slots and an address. Confirm is refused until at least one material has a weight («دست‌کم یک مورد را انتخاب کنید»).
2. Each material is 0.5 to 50 kg and the total at most 50 kg. Above the cap the UI shows «سقف هر درخواست ۵۰ کیلو است»; the API answers 422.
3. The day is today to today + 14 days by the Tehran date; the UI offers a subset. A day outside the window is 422.
4. The address is 3 to 200 characters after trimming; a blank or two-character address shows «اینجا نباید خالی باشد» or «نشانی را کامل‌تر بنویسید» and is refused by the API with 422.
5. A sixth request on the same Tehran day is refused with 409 and the UI shows «سقف درخواست‌های امروز پر شده است؛ فردا دوباره تلاش کنید». Canceled requests count toward the five.
6. On success the UI shows the estimated points (points per kg times kg) and the request appears as the next pickup on the dashboard when it is the earliest from today on (by day, then slot).

### Complete (collector)

1. Outside demo mode, completing needs `X-Collector-Key`; without it, or with a wrong one, the answer is 403 `forbidden` and nothing changes.
2. A pickup whose day is in the future cannot be completed outside demo mode (409).
3. A completed pickup is `delivered`, its weighed kg are within ±10% of each declared kg, the points equal the estimate of the weighed kg, and the wallet grows by exactly that.
4. Completing twice, or completing a canceled pickup, is 409 and pays nothing. Eight parallel completes pay once.
5. In demo mode the dashboard's «شبیه‌سازی تحویل» button completes the next pickup; it is hidden when the API reports `demo: false`.

### Cancel

1. Only a scheduled pickup can be canceled (otherwise 409; unknown id 404). Canceling pays nothing and frees no daily slot.
2. A scheduled pickup more than 7 days past its day is canceled by the hourly sweep.

### Redeem

1. «فعال‌سازی» is enabled when the balance is at least the cost, and shows «امتیاز کم دارید» otherwise.
2. At balance equal to cost the redeem succeeds and the balance becomes 0; at cost minus 1 it is refused (409) and nothing is written.
3. The confirm sheet shows the cost and «از کیف پول شما کسر می‌شود»; success shows the code (`SABZ-` plus 12 characters) with a Copy button.
4. Eight parallel redeems against a balance for one reward succeed once; for two, twice. The balance never goes negative.
5. A double click on confirm sends one request.

### My reward codes

1. Every code the citizen redeemed in this browser is listed under «کدهای من» with the reward name and a Copy button, newest first, at most 20, after a reload too.
2. The list says it is kept on this device only («فقط روی همین دستگاه نگه داشته می‌شوند»).
3. A failed redeem (409) adds nothing.
4. Copy says «کپی شد» only when the text actually reached the clipboard, also over plain HTTP where `navigator.clipboard` is unavailable.
5. A malformed value under the `sabz:codes` storage key is ignored instead of breaking the page, and a code redeemed in another tab shows up here without a reload.

### Partner code use

1. Lookup and spend need `X-Partner-Key`; unset, missing and wrong keys all get the same 403.
2. Lookup of a fresh code returns its reward and `used: null`; after a spend, `used` is the spend time.
3. A code spends once: the second spend is 409. An unknown code is 404 for both calls.
4. No full code appears in any log line; logs show `code#<sha256[:8]>`.

### Missions

1. Each mission shows its question and options; the catalogue never contains the answer.
2. A wrong answer reveals nothing and pays nothing («پاسخ نادرست است؛ دوباره امتحان کنید»); the right answer pays the mission's points once («آفرین! پاسخ درست است»).
3. Answering a done mission, right or wrong, is 409, and the card shows «انجام شد».
4. A choice outside the mission's options is 422.

### History

1. Two tabs: requests and transactions («درخواست‌ها»، «تراکنش‌ها»), with arrow-key navigation between them.
2. Requests show status («در انتظار جمع‌آوری»، «تحویل‌شده»، «لغوشده»), day, slot, items and points (or the estimate for scheduled ones).
3. Transactions show the newest 100 with signed amounts; a negative amount is a redeem.
4. Empty states: «هنوز درخواستی ثبت نکرده‌اید» and «هنوز تراکنشی ندارید» on an empty production database.

### City dashboard

1. Six KPIs, a 12-month chart, the material mix (adding up to 100%) and the district ranking.
2. The figures are labelled as sample data («داده نمایشی»), never as live, until they come from real data.
3. The district ranking equals `GET /api/leaderboard`.

### Language and theme

1. With no cookie the UI is Persian, right to left, with Persian digits. Choosing English sets the `lang=en` cookie (`SameSite=Lax`, plus `Secure` over HTTPS) and switches direction, digits and copy without losing form input.
2. Theme cycles automatic, light, dark («خودکار»، «روشن»، «تاریک»); the choice survives a reload with no flash of the other theme.
3. Signed numbers keep the sign on the correct side in Persian (`+۴۰`, not `۴۰+`).

## Boundary values

| Rule | Values | Expected | Pinned by |
|---|---|---|---|
| kg per material, low | 0.49, 0.5 | 422; 201 with `est` 25 (glass) | `kg_bounds` |
| kg per material, high | 50, 50.01, 100 | 201 with `est` 15000 (e-waste); 422; 422 | `kg_bounds` |
| Total kg | 25 + 25; 10.1 + 19.9 + 20; 25 + 25.01 | 201; 201 (float error does not refuse it); 422 naming 50 kg | `kg_bounds` |
| Items | `{}`, unknown material, 0, NaN, Infinity | 422 each (NaN and Infinity never a 500) | `kg_bounds` |
| Day window | today − 1, today, today + 14, today + 15, `2026-02-30` | 422, 201, 201, 422, 422 | `day_window` |
| Day rollover | 5 created at 23:59:59 Tehran, then 00:00:00 | 409, then 201; yesterday's day is 422 | `daily_cap_resets_at_tehran_midnight` |
| Daily cap | 5, then the 6th; 8 in parallel | 201 × 5, 409; exactly 5 succeed | `daily_cap` |
| Address | `ab`, `  ab  `, three spaces, `abc`, 200 × `a`, 201 × `a`, `   abc   ` | 422, 422, 422, 201, 201, 422, 201 stored as `abc` | `address_length` |
| Balance vs cost | 449, 450, 451 for a 450 reward | 409 with nothing written; 200 and balance 0; 200 and balance 1 | `redeem_at_exact_balance` |
| Parallel redeems | balance for 1 and for 2 tickets, 8 requests | 1 and 2 successes; balance never below the remainder | `redeem_races` |
| Tier edges | lifetime 1999, 2000, 5999, 6000 | bronze (next silver at 2000), silver, silver (next gold at 6000), gold (next null); a redeem never demotes | `tier_edges_and_empty_production_db` |
| Mission choice | −1, 0, 2, 3, 9, 10, `"x"` on a 3-option mission | 422, 200, 200, 422, 422, 422, 422 | `mission_choice_bounds` |
| Body size | 16384 bytes, 16385 bytes, streamed and by header | 200, 413 | `body_size_limit` |
| Write bucket | 10 in a burst, the 11th; refill at 1.5 s and 2 s | 429 with `Retry-After: 2`; no token, then one | `rate_limit_burst`, `rate_limit_refill` |
| Read bucket | `READ_BURST` then one more | 429 with `Retry-After: 1` | `read_bucket` |
| Pagination | `limit` 0, 201; `before` 0, 2^63, an unknown id | 422, 422, 422, 422, `[]` | `pagination` |
| Key strength | 16 characters, 32 with 1 distinct, 36 with 9 distinct, a weak key inside a comma list | startup stops | `weak_keys_stop_startup` |

## Automation pyramid

| Layer | Exists | Add next |
|---|---|---|
| Backend API and unit (`backend/test_api.py`) | 47 sections: flows, every boundary above, races, keys, migrations, health, ops, the request pipeline and log hygiene. Deterministic (fake clock, seeded jitter, fresh database per section), also shuffled. 8 of 8 planted bugs caught | Sections for each phase in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) as it lands |
| Dependency and static checks | pip-audit, npm audit, semgrep, gitleaks, hadolint, trivy, the threat brief (CI) | None needed now |
| Frontend unit | None | Vitest for the pure helpers: `formatDay` (Jalali month and year edges), `n()` with Persian digits, `signed()` (the LTR isolate), the status-to-copy map used for errors, the `api()` cache and its epoch guard (a GET sent before `refresh()` must not win), and dictionary parity (every key in both `fa` and `en`). About 15 tests, no DOM |
| API contract | Shapes are checked in `read_endpoints` and the per-endpoint sections | A test that the TypeScript types in `lib/api.ts` match real responses (for example, generate a fixture from the demo stack and type-check it) |
| End to end | None | A small Playwright smoke on the production build: dashboard renders in Persian RTL; pickup happy path; simulate delivery; redeem and see the code in «کدهای من»; mission wrong then right; language and theme persistence; one axe pass per page in both themes. About 8 tests |
| Stack smoke (`scripts/smoke.sh`) | 20 checks through the edge: health, demo flag, rate limit, container lockdown, security headers, CSP nonce, forged `X-Forwarded-For` (CI job `smoke`) | Nothing |
| Visual | `scripts/screenshots.py`: 60 captures per run (48 page shots, 4 redeem sheets, 2 saved-code shots, 4 narrow tab bars, 2 pickup-success sheets) plus a browser-problem log | Run it per release and compare with the previous set |

Keep the pyramid small: the backend suite carries the business rules; the frontend layers exist to catch rendering and wiring defects that the type check and build cannot.

## Manual regression checklist

Run on the production build with `DEMO_MODE=1` and a fresh database, before each release. Phones: 320, 360 and 390 px; tablet 768; desktop 1280 and 1440.

**Direction and language**

- [ ] First visit with no cookie: `<html lang="fa" dir="rtl">`, Persian digits, sidebar and icons mirrored.
- [ ] Switch to English with a half-filled pickup form: values kept, direction and digits switch, cookie `lang=en` set.
- [ ] A cookie `lang=xx` falls back to Persian.
- [ ] Reward codes and signed amounts stay left to right inside Persian text; a mixed Persian and Latin address truncates at the correct end.
- [ ] Dates: Persian calendar in Persian (for example the day strip across the end of a Jalali month), Gregorian in English.

**Theme**

- [ ] Light, dark and automatic, on each page; automatic follows an OS change live.
- [ ] Saved dark with OS light: hard reload shows no light frame.
- [ ] Increased contrast and reduced transparency give solid surfaces.
- [ ] Contrast of the primary button text and small coloured text meets WCAG AA in both themes.

**Layout**

- [ ] No element wider than the viewport at 320, 360 and 390 px (check elements, not only `body`, which hides overflow).
- [ ] The mobile pickup summary bar with Confirm stays pinned to the bottom of the screen and never covers the address field, also with the on-screen keyboard open.
- [ ] 767 to 768 px: the sidebar appears and the tab bar goes, with no double navigation.
- [ ] Touch targets at least 44 by 44 px (steppers, chips, header buttons).
- [ ] 200% text zoom at 360 px: no clipped buttons.

**Keyboard and screen reader**

- [ ] A skip link is the first Tab stop on every page.
- [ ] The whole pickup flow and the redeem flow work with the keyboard only; focus returns to a sensible element after a sheet closes.
- [ ] Every sheet is a dialog with an accessible name; Escape closes it.
- [ ] Quantity buttons have names; slots expose `aria-pressed`; quiz results and the points toast are announced.
- [ ] With VoiceOver (iOS) and TalkBack (Android) in Persian: labels are Persian, with no English tokens.

**Motion**

- [ ] With reduced motion: no springs or counters animate; sheets cross-fade.

**Network**

- [ ] Offline after visiting a page: the cached page stays, with an error only where there is nothing to show.
- [ ] A slow network (throttled): a stalled request gives up after 15 s with a localized error and re-enabled buttons.
- [ ] A 200 response that is not JSON (a captive portal page) shows the error box, not a crash.
- [ ] 429 after a quick burst on missions shows «کمی صبر کنید و دوباره تلاش کنید» and recovers.

**Copy to clipboard**

- [ ] Over HTTPS: Copy puts the code on the clipboard and says «کپی شد».
- [ ] Over plain HTTP from another device on the LAN (`http://<host-ip>:3026`): the fallback copies, or the label does not claim success.

## Running the smoke script

```bash
# backend only: health, catalog demo flag, rate limit, backend container lockdown
scripts/smoke.sh
# also through the edge: container lockdown of all three, security headers, CSP nonce, forged X-Forwarded-For
scripts/smoke.sh full
```

| Variable | Default | Meaning |
|---|---|---|
| `API_URL` | `http://127.0.0.1:${API_PORT:-8026}` | Backend base URL |
| `WEB_URL` | `http://127.0.0.1:${WEB_PORT:-3026}` | Edge base URL |
| `EXPECT_DEMO` | `${DEMO_MODE:-0}` | The `demo` flag `/api/catalog` must report |
| `PROJECT` | compose's default | Compose project for the container checks |
| `DOCKER` | `docker` | Docker command, for example `docker --context default`; container checks are skipped without it |

Output is one `PASS` or `FAIL` line per check; exit 1 on any failure, 2 on bad usage. The burst check sends 12 POSTs, so expect the write bucket of that client to be empty for a few seconds afterwards.

## Screenshots

`scripts/screenshots.py` drives one headless Chrome over the DevTools protocol and captures every page in both themes, both languages and two sizes (390 by 844 and 1280 by 800), plus the redeem confirm sheet (mobile), the pickup success sheet, the narrow (320 by 640) dashboard tab bar, and for light/fa one real redeem: the code sheet and the saved-codes list. It also writes `issues.json` with console errors and warnings, exceptions, CSP and audit issues, failed or 400+ requests, and horizontal overflow.

```bash
# a throwaway demo stack: the pickup step creates 2 pickups per run, and the API allows 5 a day
DEMO_MODE=1 WEB_PORT=3126 API_PORT=8126 docker compose -p sabzshots up -d --build --wait
backend/.venv/bin/pip install websockets            # the script's one dependency, not in the lock files
backend/.venv/bin/python scripts/screenshots.py http://127.0.0.1:3126 shots
backend/.venv/bin/python scripts/screenshots.py http://127.0.0.1:3126 shots --chrome "$(command -v google-chrome)"
docker compose -p sabzshots down -v
```

Files are named `<page>-<light|dark>-<fa|en>-<mobile|desktop>.png`, plus `rewards-redeem-*`, `pickup-done-*`, `rewards-code-*`, `rewards-mycodes-*` and `home-*-narrow`. `--chrome` defaults to `/usr/bin/google-chrome`. To refresh the documentation images, copy the files with the names used in [README.md](README.md) and [UI_UX.md](UI_UX.md) into `docs/screenshots/`.
