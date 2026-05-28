# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This repo contains two apps that share data formats and features:

1. **Desktop app** — `dashboard.py` (~3,300 lines), GTK4/Python, runs on Linux Mint 22+/Ubuntu 24.04+
2. **Web app** — `web/`, PHP + vanilla HTML/CSS/JS, hosted at `md.paullintott.uk` on DirectAdmin

Both apps show the same seven tabs: Spurgeon devotional, News, Weather, Bible, Prayer, Notes, Sermons. The desktop app additionally has a Calendar tab (Google Calendar). The web app adds multi-user support, sub-points on prayers, M'Cheyne readings, and an admin panel.

## Running the desktop app

```bash
python3 dashboard.py
```

First run launches a setup wizard for Google credentials. No build step needed.

**Python dependencies:**
```bash
pip3 install requests google-auth google-auth-oauthlib google-api-python-client google-auth-httplib2 --break-system-packages
```

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
- **Browser:** PHP session (`$_SESSION['user']`) set on login. Remember-me cookie (`remember_me`) backed by `data/remember_tokens.json` (64-char random hex, 30-day expiry, rotated on every use).
- **Desktop app:** HTTP Basic Auth — credentials verified against `.htpasswd` (APR1-MD5 hashes; bcrypt dropped for shared-hosting compatibility) via `verify_htpasswd()`. Sets `$_MD_AUTH_USER` for the request scope; never touches the session.

`config.php` defines `ADMIN_USER` ('paul') and `HTPASSWD_FILE`. `helpers.php` provides `current_user()` and `user_data_dir()`.

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
- `access.php` — user management: `list`, `list_users`, `approve` (generates 16-char random password), `deny`, `delete_user`, `change_password`

**Access request system:** `request.php` is public (auth exempt). Submissions go to `data/access_requests.json`. Rate limited to 3/IP/hour via `data/rate_limit.json`. Admin approves/denies via `api/access.php`.

**Frontend (`web/static/app.js`):** Vanilla JS, no framework. Key globals: `ALL_TABS`, `TAB_META`, `window.INIT_PREFS`, `window.IS_ADMIN`. Sidebar is built dynamically from tab order/visibility prefs. Scripture refs in Spurgeon text are linkified to open the Bible tab. M'Cheyne readings calculated client-side.

## Development workflow

- Edits are made in-place in this working directory. Paul reviews all changes before committing — **do not commit autonomously**.
- No "Co-Authored-By" lines in commit messages.

## Known issues

**Spurgeon notes cursor (desktop):** `spurgeon_notes_view` uses `.spurgeon-notes` CSS (dark sepia `#2d1b0e`, golden text `#d4a96a`) to make the cursor visible. Root cause: GTK4 makes the cursor white when the system is in dark mode but the app uses a light theme. All direct cursor-colour CSS overrides have failed — the sepia background is a workaround. CSS lives in `_apply_css()`.
