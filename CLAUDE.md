# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This repo contains two apps that share data formats and features:

1. **Desktop app** — `dashboard.py` (~3,300 lines), GTK4/Python, runs on Linux Mint 22+/Ubuntu 24.04+
2. **Web app** — `web/`, PHP + vanilla HTML/CSS/JS, hosted at `md.paullintott.uk` on DirectAdmin

Both apps show the same tabs: Daily Bible, Spurgeon devotional, Systematics (Theology), News, Weather, Bible, Prayer, Notes, Sermons, Resources. The desktop app additionally has a Calendar tab (Google Calendar). The web app adds multi-user support, sub-points on prayers, M'Cheyne readings, and an admin panel.

## Running the desktop app

```bash
python3 dashboard.py
```

First run launches a setup wizard for Google credentials. No build step needed.

**Python dependencies:**
```bash
pip3 install requests google-auth google-auth-oauthlib google-api-python-client google-auth-httplib2 --break-system-packages
```

**Building the .deb:** `tools/build_deb.sh [version]` (version defaults to today, `YYYY.MM.DD`) writes `morning-dashboard_<version>_all.deb` to the repo root. It installs to `/usr/lib/morning-dashboard/` with a `/usr/bin/morning-dashboard` launcher and generates its own `.desktop` file — the repo's `morning-dashboard.desktop` is only the local dev launcher (points at this checkout).

**Data location:** `DATA_DIR` in `dashboard.py` holds `credentials.json`, `token.json`, `prayers.json` and the `prayer_*.json` calendars. It's the checkout directory when writable (dev), else `~/.local/share/morning-dashboard/` (installed .deb). Prefs, notes and sermons are always under `~/.config/morning-dashboard/`.

## Web app

No build pipeline — plain PHP. To deploy: upload `web/` contents to the DirectAdmin subdomain's `public_html`. The `data/` directory must be writable (755). **Delete any `index.html` the host places there** — it takes priority over `index.php` and blocks the app.

Local development can be done by reading/editing files directly; the live site is at `md.paullintott.uk`.

## Desktop app architecture

The entire UI is in a single file: `dashboard.py`. Key classes:

- `MorningDashboard(Gtk.ApplicationWindow)` — main window; builds all tabs
- `SetupWizard(Gtk.ApplicationWindow)` — first-run Google credentials wizard

**Layout (GTK4 widget tree):**
```
root (Gtk.Box, vertical)
├── header (Gtk.Box, horizontal)
└── body (Gtk.Box, horizontal)
    ├── _sidebar (Gtk.Box)
    │   ├── _icon_col (always visible, ~44px fixed)  — emoji icon buttons
    │   └── _label_revealer (Gtk.Revealer SLIDE_RIGHT) — collapses to hide labels
    └── stack (Gtk.Stack, CROSSFADE) — tab content pages
```

**Key methods:**
- `_build_sidebar_buttons()` — creates icon + label buttons per tab
- `_switch_tab(key)` — sets stack visible child, updates active CSS classes and indicator bars
- `_toggle_sidebar()` — toggles `_label_revealer`, updates collapse button label
- `_apply_tab_order()` / `_apply_tab_visibility()` — rebuild sidebar from prefs
- `_apply_css()` — generates all CSS including per-tab accent colours and dark/light theme
- `_on_close_request()` — saves window size to prefs before closing
- `_prayer_push_to_web()` / `_prayer_pull_from_web()` — prayer sync (run in daemon threads; use `GLib.idle_add` for any UI updates)
- Tab builders: `_build_spurgeon_tab()`, `_build_news_tab()`, `_build_weather_tab()`, `_build_sermon_tab()`, `_build_calendar_tab()`, `_build_bible_tab()`, `_build_prayer_tab()`, `_build_notes_tab()`

**Threading rule:** All GTK UI updates from background threads must be dispatched via `GLib.idle_add`.

**Sidebar button dicts:** `self._sidebar_buttons` (key → `(icon_row, icon_btn, label_btn)`), `self._sidebar_indicators` (key → indicator `Box`).

**Per-tab accent colours:** spurgeon=#f0a500, news=#4a9eff, weather=#00bcd4, sermons=#66bb6a, calendar=#ab47bc, bible=#ffd54f, prayer=#ef5350, notes=#ff7043

**Prefs file:** `~/.config/morning-dashboard/prefs.json` — includes font_size, theme, weather_location, enabled_calendars, visible_tabs, tab_order, window_width/height, web_url/user/pass.

**Google OAuth:** credentials in `credentials.json` and `token.json` (in project dir, gitignored). Scopes: Drive, Calendar, userinfo.

## Web app architecture

**Entry point:** `web/index.php` — PHP shell that injects `window.INIT_PREFS` and `window.IS_ADMIN` as globals for `app.js`. Tab panels are empty `<div>` elements; all content is rendered client-side.

**Auth:** Two auth paths, both handled in `helpers.php` by `require_auth()` (called automatically at include time):
- **Browser:** PHP session (`$_SESSION['user']`) set on login. Remember-me cookie (`remember_me`) backed by `data/remember_tokens.json` (64-char random hex, 10-year expiry — deliberately "effectively unlimited" — rotated on every use). Sessions store `auth_time`; `revoke_logins()` (on password change/reset and account deletion) deletes the user's remember-me tokens and records a timestamp in `data/logins_revoked.json`, and `require_auth()` drops any session that logged in before it. The browser that changed its own password stays logged in.
- **Desktop app:** HTTP Basic Auth — credentials verified against `.htpasswd` (APR1-MD5 hashes; bcrypt dropped for shared-hosting compatibility) via `verify_htpasswd()`. Sets `$_MD_AUTH_USER` for the request scope; never touches the session. Failures count toward the same per-IP lockout as the login form (5 in 15 min, `data/login_attempts.json`); once locked, Basic Auth gets HTTP 429 even with the right password.

`config.php` defines `ADMIN_USER` ('paul') and `HTPASSWD_FILE`. `helpers.php` provides `current_user()`, `is_authenticated()`, and `user_data_dir()`.

**Guest (logged-out) view:** `require_auth()` lets unauthenticated visitors load `index.php` instead of redirecting to `/login.php`, plus logged-out GET requests to `api/spurgeon.php` and `api/spurgeon_modern.php` (both stateless/read-only). `index.php` detects this via `is_authenticated()`, sets `window.IS_GUEST = true`, and forces a minimal config: only the `spurgeon` tab, no prefs loaded/saved, no settings modal, "Log in" link instead of user/logout. `app.js` checks `IS_GUEST` to skip rendering the notes textarea and Community Comments panel, and to skip the per-user API calls (`spurgeon_notes.php`, `spurgeon_comments.php`) that would 401.

**CSRF protection:** After `require_auth()`, `helpers.php` checks that any POST/DELETE/PUT from a session-authenticated user includes `X-Requested-With: XMLHttpRequest`. Basic Auth requests (desktop app) are exempt. The `api()` function in `app.js` sends this header on every fetch call.

**Per-user data isolation:** All user data lives under `web/data/users/{username}/`. The directory is created automatically on first request. `config.php` and `helpers.php` are blocked from direct web access by `.htaccess`.

**API endpoints** (`web/api/`):
- `spurgeon.php` — scrapes romans45.org; no cache (stateless)
- `spurgeon_notes.php` / `notes.php` — per-user text storage
- `prayers.php` — GET/POST per-user prayers (nested with `children` sub-points)
- `prefs.php` — per-user prefs; preserves `api_bible_key` if submitted value is empty
- `bible.php` — bible-api.com (free) + rest.api.bible (CSB/NLT/NIV). The `api_bible_key` is stored server-side only; the browser only receives `api_bible_key_set: bool`
- `news.php` — BBC/Hacker News RSS
- `weather.php` — Open-Meteo (no key needed)
- `sermons.php` — per-user sermon files
- `access.php` — user management: `list`, `list_users`, `approve` (writes the password hash chosen at request time), `deny`, `reset_password` (admin; generates 16-char random password), `delete_user`, `change_password` (requires `current_password`; wrong guesses count toward the login lockout), `set_email`

**Access request system:** `request.php` is public (auth exempt). Submissions go to `data/access_requests.json`. Rate limited to 3/IP/hour via `data/rate_limit.json`. Admin approves/denies via `api/access.php`.

**Frontend (`web/static/app.js`):** Vanilla JS, no framework. Key globals: `ALL_TABS`, `TAB_META`, `window.INIT_PREFS`, `window.IS_ADMIN`. Sidebar is built dynamically from tab order/visibility prefs. Scripture refs in Spurgeon text are linkified to open the Bible tab. M'Cheyne readings calculated client-side.

## Daily Bible tab

Shows three readings a day with full text: a New Testament portion (pericope-based, 365 days), a Psalm (1–150 cycling, Psalm 119 over 4 days) and 2–3 verses of Proverbs (whole book per year). The plan tables (`DAILY_NT_PLAN` / `DAILY_PSALM_PLAN` / `DAILY_PROV_PLAN`, entries `[label, [[bookId, chapter, from, to], ...]]`) are **generated, not hand-edited** — they live in both `web/static/app.js` and `dashboard.py`. To change the NT divisions edit `tools/nt_daily_readings.txt` (one day per line) and run `python3 tools/gen_daily_plan.py --js` / `--py`, which validates every NT verse is covered exactly once and prints the tables to paste in. No new API: both apps fetch whole chapters via the existing Bible code and filter the verse range client-side.

## Development workflow

- Edits are made in-place in this working directory. Paul reviews all changes before committing — **do not commit autonomously**.
- No "Co-Authored-By" lines in commit messages.

## Known issues

**Spurgeon notes cursor (desktop):** `spurgeon_notes_view` uses `.spurgeon-notes` CSS (dark sepia `#2d1b0e`, golden text `#d4a96a`) to make the cursor visible. Root cause: GTK4 makes the cursor white when the system is in dark mode but the app uses a light theme. All direct cursor-colour CSS overrides have failed — the sepia background is a workaround. CSS lives in `_apply_css()`.
