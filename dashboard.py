#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango, Gio
import requests
import datetime
import threading
import json
import os

# ── Google Drive helper ───────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
CREDENTIALS    = os.path.expanduser("~/morning-dashboard/credentials.json")
TOKEN_FILE     = os.path.expanduser("~/morning-dashboard/token.json")
DRIVE_FOLDER   = "Morning Dashboard — Sermons"

def get_drive_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)

def get_or_create_folder(service, name):
    """Return the Drive folder ID, creating it if needed."""
    q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
         f"and trashed=false")
    results = service.files().list(q=q, fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]

def sync_sermons_to_drive(sermons_dir, status_cb):
    """Upload all sermon .txt files to Drive. Calls status_cb(msg) on progress."""
    try:
        from googleapiclient.http import MediaFileUpload
        status_cb("Connecting to Google Drive…")
        service   = get_drive_service()
        folder_id = get_or_create_folder(service, DRIVE_FOLDER)

        # Get existing files in folder to avoid duplicates
        q = f"'{folder_id}' in parents and trashed=false"
        existing = service.files().list(q=q, fields="files(id,name)").execute()
        existing_map = {f["name"]: f["id"] for f in existing.get("files", [])}

        files = [f for f in os.listdir(sermons_dir) if f.endswith(".txt")]
        if not files:
            status_cb("No sermons to sync.")
            return

        for i, fname in enumerate(files):
            status_cb(f"Uploading {i+1}/{len(files)}: {fname}")
            fpath = os.path.join(sermons_dir, fname)
            media = MediaFileUpload(fpath, mimetype="text/plain")
            if fname in existing_map:
                service.files().update(
                    fileId=existing_map[fname], media_body=media
                ).execute()
            else:
                meta = {"name": fname, "parents": [folder_id]}
                service.files().create(
                    body=meta, media_body=media, fields="id"
                ).execute()

        status_cb(f"✅ Synced {len(files)} sermon(s) to Google Drive!")
    except Exception as e:
        status_cb(f"❌ Sync failed: {e}")

# ── Calendar helper ───────────────────────────────────────────────────────────

def fetch_calendar_list():
    """Return list of (id, name) for all calendars."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        if not os.path.exists(TOKEN_FILE):
            return []
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        cal = build("calendar", "v3", credentials=creds)
        items = cal.calendarList().list().execute().get("items", [])
        return [(c["id"], c.get("summary", c["id"])) for c in items]
    except Exception:
        return []

def fetch_calendar_events(enabled_cal_ids=None):
    """Return events for the next 7 days from selected calendars."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        cal = build("calendar", "v3", credentials=creds)

        now   = datetime.datetime.now(datetime.timezone.utc)
        start = datetime.datetime(now.year, now.month, now.day).isoformat() + "Z"
        end   = (datetime.datetime(now.year, now.month, now.day)
                 + datetime.timedelta(days=7)).isoformat() + "Z"

        cal_list  = cal.calendarList().list().execute()
        calendars = cal_list.get("items", [])

        all_events = []
        for calendar in calendars:
            cal_id   = calendar["id"]
            cal_name = calendar.get("summary", cal_id)
            # Skip if not in enabled list (when a list is provided)
            if enabled_cal_ids is not None and cal_id not in enabled_cal_ids:
                continue
            try:
                result = cal.events().list(
                    calendarId=cal_id,
                    timeMin=start,
                    timeMax=end,
                    singleEvents=True,
                    orderBy="startTime"
                ).execute()
                for e in result.get("items", []):
                    summary = e.get("summary", "(No title)")
                    start_e = e.get("start", {})
                    if "dateTime" in start_e:
                        dt = datetime.datetime.fromisoformat(
                            start_e["dateTime"].replace("Z", "+00:00"))
                        sort_key = dt.replace(tzinfo=None)
                        time_str = dt.strftime("%H:%M")
                        day_str  = dt.strftime("%A, %d %B")
                    else:
                        dt = datetime.date.fromisoformat(start_e["date"])
                        sort_key = datetime.datetime(dt.year, dt.month, dt.day)
                        time_str = "All day"
                        day_str  = dt.strftime("%A, %d %B")
                    all_events.append((sort_key, day_str, time_str, summary, cal_name))
            except Exception:
                pass

        all_events.sort(key=lambda x: x[0])
        return all_events
    except Exception as e:
        return [(None, "Error", "", str(e), "")]

# ── Bible helper ──────────────────────────────────────────────────────────────

BIBLE_BOOKS = [
    ("Genesis","GEN",50),("Exodus","EXO",40),("Leviticus","LEV",27),
    ("Numbers","NUM",36),("Deuteronomy","DEU",34),("Joshua","JOS",24),
    ("Judges","JDG",21),("Ruth","RUT",4),("1 Samuel","1SA",31),
    ("2 Samuel","2SA",24),("1 Kings","1KI",22),("2 Kings","2KI",25),
    ("1 Chronicles","1CH",29),("2 Chronicles","2CH",36),("Ezra","EZR",10),
    ("Nehemiah","NEH",13),("Esther","EST",10),("Job","JOB",42),
    ("Psalms","PSA",150),("Proverbs","PRO",31),("Ecclesiastes","ECC",12),
    ("Song of Solomon","SNG",8),("Isaiah","ISA",66),("Jeremiah","JER",52),
    ("Lamentations","LAM",5),("Ezekiel","EZK",48),("Daniel","DAN",12),
    ("Hosea","HOS",14),("Joel","JOL",3),("Amos","AMO",9),
    ("Obadiah","OBA",1),("Jonah","JON",4),("Micah","MIC",7),
    ("Nahum","NAH",3),("Habakkuk","HAB",3),("Zephaniah","ZEP",3),
    ("Haggai","HAG",2),("Zechariah","ZEC",14),("Malachi","MAL",4),
    ("Matthew","MAT",28),("Mark","MRK",16),("Luke","LUK",24),
    ("John","JHN",21),("Acts","ACT",28),("Romans","ROM",16),
    ("1 Corinthians","1CO",16),("2 Corinthians","2CO",13),
    ("Galatians","GAL",6),("Ephesians","EPH",6),("Philippians","PHP",4),
    ("Colossians","COL",4),("1 Thessalonians","1TH",5),("2 Thessalonians","2TH",3),
    ("1 Timothy","1TI",6),("2 Timothy","2TI",4),("Titus","TIT",3),
    ("Philemon","PHM",1),("Hebrews","HEB",13),("James","JAS",5),
    ("1 Peter","1PE",5),("2 Peter","2PE",3),("1 John","1JN",5),
    ("2 John","2JN",1),("3 John","3JN",1),("Jude","JUD",1),
    ("Revelation","REV",22),
]

BIBLE_TRANSLATIONS = [
    ("World English Bible", "web"),
    ("King James Version", "kjv"),
    ("American Standard Version", "asv"),
    ("Bible in Basic English", "bbe"),
    ("Darby Bible", "darby"),
    ("Young's Literal Translation (NT)", "ylt"),
    ("Open English Bible (US)", "oeb-us"),
    ("Open English Bible (UK)", "oeb-cw"),
    ("World English Bible (British)", "webbe"),
    ("Douay-Rheims 1899", "dra"),
]

def fetch_esv_chapter(book_id, chapter, translation="web"):
    """Fetch a chapter from bible-api.com in paragraph format."""
    try:
        url = f"https://bible-api.com/data/{translation}/{book_id}/{chapter}"
        r = requests.get(url, timeout=10,
                         headers={"User-Agent": "MorningDashboard/1.0"})
        if r.status_code == 200:
            data = r.json()
            verses = data.get("verses", [])
            if verses:
                parts = []
                for v in verses:
                    parts.append(f"[{v['verse']}] {v['text'].strip()}")
                paragraphs = []
                chunk = []
                for i, part in enumerate(parts):
                    chunk.append(part)
                    if (i + 1) % 5 == 0:
                        paragraphs.append(" ".join(chunk))
                        chunk = []
                if chunk:
                    paragraphs.append(" ".join(chunk))
                return "\n\n".join(paragraphs)
            return "No text available for this translation."
        return f"Could not load chapter (HTTP {r.status_code})"
    except Exception as e:
        return f"Error: {e}"

# ── Spurgeon helper ──────────────────────────────────────────────────────────

def fetch_spurgeon(date=None):
    """Fetch Morning & Evening reading from romans45.org archive."""
    import re
    if date is None:
        date = datetime.date.today()

    month = date.strftime("%m")
    day   = date.strftime("%d")

    results = []
    try:
        r = requests.get(
            "https://www.romans45.org/morn_eve/m_e.html",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 MorningDashboard/1.0"}
        )
        if r.status_code != 200:
            return f"Could not load archive (HTTP {r.status_code})"

        html = r.text

        for period, label in [("AM", "☀️ Morning"), ("PM", "🌙 Evening")]:
            anchor = f'{month}/{day}/{period}'
            # Find position of anchor in page
            pos = html.find(f'"{anchor}"')
            if pos == -1:
                pos = html.find(f"'{anchor}'")
            if pos == -1:
                results.append(f"{label}\n\nReading not found.")
                continue

            # Find the next anchor position to use as boundary
            next_pos = html.find('"', pos + 10)
            # Find next date anchor after current one
            next_anchor_match = re.search(
                r'"\d\d/\d\d/[AP]M"', html[pos + 10:]
            )
            if next_anchor_match:
                chunk = html[pos: pos + 10 + next_anchor_match.start()]
            else:
                chunk = html[pos: pos + 6000]

            # Replace decorative initial letter images with the actual letter
            chunk = re.sub(
                r'<img[^>]+/images/([a-z])\.gif[^>]*>',
                lambda m: m.group(1).upper(),
                chunk, flags=re.IGNORECASE
            )

            # Strip HTML tags
            text = re.sub(r'<script[^>]*>.*?</script>', '', chunk, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>',  '', text,   flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'&nbsp;', ' ', text)
            text = re.sub(r'&amp;',  '&', text)
            text = re.sub(r'&quot;', '"', text)
            text = re.sub(r'&#\d+;', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()

            if len(text) > 50:
                # Strip the anchor reference from the start e.g. name="05/03/AM">
                text = re.sub(r'^[^>]*>\s*', '', text)
                # Strip any trailing anchor tag
                text = re.sub(r'\s*<?\s*a\s+name=.*$', '', text, flags=re.IGNORECASE).strip()
                results.append(f"{label}\n\n{text[:3000]}")
            else:
                results.append(f"{label}\n\nReading not available.")

    except Exception as e:
        return f"Error loading reading: {e}"

    return "\n\n─────────────────────────────────\n\n".join(results)

# ── News helper ───────────────────────────────────────────────────────────────

NEWS_SOURCES = {
    "AI News":   "https://feeds.feedburner.com/TheHackersNews",
    "Tech News": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "BBC News":  "https://feeds.bbci.co.uk/news/rss.xml",
}

def fetch_news(url):
    try:
        r = requests.get(url, timeout=10,
                         headers={"User-Agent": "MorningDashboard/1.0"})
        import re
        items = re.findall(r'<item>(.*?)</item>', r.text, re.DOTALL)
        results = []
        for item in items[:10]:
            title = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
            link  = re.search(r'<link>(.*?)</link>',  item, re.DOTALL)
            if title:
                t = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title.group(1)).strip()
                l = link.group(1).strip() if link else ""
                results.append((t, l))
        return results
    except Exception as e:
        return [(f"Error: {e}", "")]

# ── Preferences helpers ───────────────────────────────────────────────────────

PREFS_FILE = os.path.expanduser("~/.config/morning-dashboard/prefs.json")

def load_prefs():
    defaults = {"font_size": 13, "theme": "dark", "weather_location": "", "weather_country": "GB", "enabled_calendars": []}
    try:
        with open(PREFS_FILE) as f:
            data = json.load(f)
            defaults.update(data)
            return defaults
    except Exception:
        return defaults

def save_prefs(prefs):
    os.makedirs(os.path.dirname(PREFS_FILE), exist_ok=True)
    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f)

# ── Main Window ───────────────────────────────────────────────────────────────

class MorningDashboard(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="☀️  Morning Dashboard")
        self.set_default_size(900, 650)
        self.set_resizable(True)
        self.set_size_request(600, 400)

        self.prefs = load_prefs()
        self.font_size = self.prefs.get("font_size", 13)
        self.theme = self.prefs.get("theme", "dark")
        self.weather_location = self.prefs.get("weather_location", "")
        self.weather_lat      = self.prefs.get("weather_lat", None)
        self.weather_lon      = self.prefs.get("weather_lon", None)
        self.enabled_calendars = self.prefs.get("enabled_calendars", [])

        # Dynamic CSS provider (rebuilt when settings change)
        self.css_provider = Gtk.CssProvider()
        self._apply_css()

        # Root layout
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.add_css_class("header-bar")

        title_lbl = Gtk.Label(label="☀️  Morning Dashboard")
        title_lbl.add_css_class("app-title")
        title_lbl.set_halign(Gtk.Align.START)

        today = datetime.date.today().strftime("%A, %d %B %Y")
        date_lbl = Gtk.Label(label=today)
        date_lbl.add_css_class("date-label")
        date_lbl.set_hexpand(True)

        prefs_btn = Gtk.Button(label="⚙️ Preferences")
        prefs_btn.add_css_class("prefs-button")
        prefs_btn.connect("clicked", self._open_prefs)

        header.append(title_lbl)
        header.append(date_lbl)
        header.append(prefs_btn)
        root.append(header)

        # Notebook (tabs)
        self.notebook = Gtk.Notebook()
        self.notebook.set_vexpand(True)
        root.append(self.notebook)

        self._build_spurgeon_tab()
        self._build_news_tab()
        self._build_weather_tab()
        self._build_sermon_tab()
        self._build_calendar_tab()
        self._build_bible_tab()
        self._build_prayer_tab()

    # ── CSS ───────────────────────────────────────────────────────────────────

    def _apply_css(self):
        fs = self.font_size
        dark = self.theme == "dark"

        # Remove old provider and add fresh one to force full restyle
        try:
            Gtk.StyleContext.remove_provider_for_display(
                self.get_display(), self.css_provider
            )
        except Exception:
            pass
        self.css_provider = Gtk.CssProvider()

        # Colours
        bg          = "#1a1a2e" if dark else "#f0f0f5"
        header_bg   = "#16213e" if dark else "#dde3f0"
        header_border = "#0f3460" if dark else "#b0bcd8"
        text        = "#e0e0e0" if dark else "#1a1a2e"
        subtext     = "#a0a0c0" if dark else "#555570"
        reading     = "#d0d0e8" if dark else "#2a2a3e"
        tab_bg      = "#16213e" if dark else "#dde3f0"
        tab_active  = "#0f3460" if dark else "#c0ccec"
        accent      = "#e94560" if dark else "#c0392b"
        btn_bg      = "#0f3460" if dark else "#c0ccec"
        news_text   = "#c0c0e0" if dark else "#333355"
        weather_bg  = "#16213e" if dark else "#dde3f0"
        status_col  = "#6060a0" if dark else "#8888aa"

        css = f"""
            window {{ background-color: {bg}; }}
            .header-bar {{
                background-color: {header_bg};
                padding: 12px 20px;
                border-bottom: 1px solid {header_border};
            }}
            .app-title {{ font-size: 20px; font-weight: bold; color: {text}; }}
            .date-label {{ font-size: 12px; color: {subtext}; padding: 0 12px; }}
            .prefs-button {{
                background-color: {btn_bg};
                color: {subtext};
                font-size: 12px;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
            }}
            .prefs-button:hover {{ background-color: {accent}; color: #ffffff; }}
            notebook {{ background-color: {bg}; }}
            notebook tab {{
                background-color: {tab_bg};
                color: {subtext};
                padding: 8px 20px;
                border: none;
            }}
            notebook tab:checked {{
                background-color: {tab_active};
                color: {accent};
                border-bottom: 2px solid {accent};
            }}
            .tab-content {{ background-color: {bg}; padding: 20px; }}
            .section-title {{
                font-size: 16px; font-weight: bold;
                color: {accent}; margin-bottom: 10px;
            }}
            .reading-text {{
                font-size: {fs}px;
                color: {reading};
                line-height: 1.8;
            }}
            .reading-text text {{
                font-size: {fs}px;
                color: {reading};
                background-color: {bg};
            }}
            .news-button {{
                background-color: transparent;
                color: {news_text};
                font-size: {fs - 1}px;
                padding: 6px 10px;
                border: none;
                border-radius: 4px;
            }}
            .news-button:hover {{ background-color: {tab_active}; color: {text}; }}
            .source-label {{
                font-size: {fs - 2}px; font-weight: bold;
                color: {accent}; padding: 10px 0 4px 0;
            }}
            .status-label {{
                color: {status_col}; font-style: italic;
                font-size: {fs - 1}px; padding: 20px;
            }}
            .weather-box {{
                background-color: {weather_bg};
                border-radius: 12px; padding: 20px; margin: 10px;
            }}
            .weather-temp {{ font-size: 48px; font-weight: bold; color: {text}; }}
            .weather-desc {{ font-size: 14px; color: {subtext}; }}
            .forecast-row {{
                background-color: {weather_bg};
                border-radius: 8px;
                padding: 8px 16px;
            }}
            .forecast-day {{ font-size: {fs}px; color: {text}; font-weight: bold; }}
            .forecast-hi  {{ font-size: {fs}px; color: #e94560; }}
            .forecast-lo  {{ font-size: {fs}px; color: {subtext}; }}
            .sermon-toolbar {{
                background-color: {header_bg};
                padding: 8px 12px;
                border-radius: 8px;
                margin-bottom: 8px;
            }}
            .sermon-title-entry {{
                font-size: {fs}px;
                background-color: {tab_active};
                color: {text};
                border: 1px solid {header_border};
                border-radius: 6px;
                padding: 6px 10px;
            }}
            .sermon-btn {{
                background-color: {btn_bg};
                color: {subtext};
                font-size: 12px;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                margin-left: 4px;
            }}
            .sermon-btn:hover {{ background-color: {accent}; color: #ffffff; }}
            .sermon-list-item {{
                background-color: {tab_active};
                border-radius: 6px;
                padding: 6px 10px;
                margin-bottom: 2px;
                color: {text};
                font-size: {fs}px;
            }}
            .sermon-list-item:hover {{ background-color: {accent}; color: #ffffff; }}
            textview {{
                color: {text};
                background-color: {bg};
            }}
            textview text {{
                color: {text};
                background-color: {bg};
            }}
            .cal-event-time {{
                font-size: {fs - 1}px;
                color: {subtext};
                min-width: 160px;
            }}
            .cal-event-title {{
                font-size: {fs}px;
                color: {text};
            }}
            .cal-event-row {{
                background-color: {tab_active};
                border-radius: 6px;
                padding: 8px 12px;
            }}
            .cal-day-header {{
                font-size: {fs - 1}px;
                font-weight: bold;
                color: {accent};
                padding: 12px 0 4px 0;
            }}
            .bible-verse {{
                font-size: {fs}px;
                color: {reading};
                line-height: 1.9;
                background-color: {bg};
            }}
            .bible-verse text {{
                color: {reading};
                background-color: {bg};
            }}
            .prayer-item {{
                background-color: {tab_active};
                border-radius: 6px;
                padding: 6px 12px;
                color: {text};
                font-size: {fs}px;
            }}
            .prayer-item:hover {{ background-color: {header_border}; }}
            .prayer-done {{
                color: {subtext};
                font-size: {fs}px;
                text-decoration: line-through;
            }}
            .bible-verse-num {{
                font-size: {fs - 2}px;
                color: {accent};
                font-weight: bold;
            }}
        """.encode()
        self.css_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _get_signed_in_account(self):
        """Return the email of the currently signed-in Google account, or None."""
        try:
            if not os.path.exists(TOKEN_FILE):
                return None
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            import requests as req
            r = req.get(
                "https://www.googleapis.com/oauth2/v1/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=5
            )
            return r.json().get("email", "Signed in")
        except Exception:
            return "Signed in"

    def _google_signin(self, dialog, box, cal_header):
        """Delete token and trigger fresh OAuth login."""
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        self.enabled_calendars = []

        def do_signin():
            try:
                get_drive_service()  # triggers browser OAuth flow
                account = self._get_signed_in_account_from_token()
                GLib.idle_add(self._after_signin, account, dialog)
            except Exception as e:
                GLib.idle_add(self.google_status_lbl.set_text, f"Sign in failed: {e}")

        threading.Thread(target=do_signin, daemon=True).start()
        self.google_status_lbl.set_text("Opening browser for sign in…")

    def _get_signed_in_account_from_token(self):
        """Read the account email from token after sign in."""
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            # Use the userinfo endpoint to get email
            import requests as req
            r = req.get(
                "https://www.googleapis.com/oauth2/v1/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=5
            )
            return r.json().get("email", "Unknown")
        except Exception:
            return "Signed in"

    def _after_signin(self, account, dialog):
        self.google_status_lbl.set_text(f"Signed in as: {account}")
        # Reload calendar tab
        threading.Thread(target=self._load_calendar, daemon=True).start()

    def _google_signout(self):
        """Remove token file to sign out."""
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        self.enabled_calendars = []
        self.prefs["enabled_calendars"] = []
        save_prefs(self.prefs)
        if hasattr(self, "google_status_lbl"):
            self.google_status_lbl.set_text("Not signed in")

    # ── Preferences dialog ────────────────────────────────────────────────────

    def _open_prefs(self, btn):
        dialog = Gtk.Dialog(title="Preferences", transient_for=self, modal=True)
        dialog.set_default_size(420, 480)

        outer = Gtk.ScrolledWindow()
        outer.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(24)
        box.set_margin_end(24)

        # ── Google Account section ────────────────────────────────────────────
        google_header = Gtk.Label(label="GOOGLE ACCOUNT")
        google_header.add_css_class("source-label")
        google_header.set_halign(Gtk.Align.START)
        box.append(google_header)

        google_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        # Show current signed-in account
        signed_in = self._get_signed_in_account()
        self.google_status_lbl = Gtk.Label(
            label=f"Signed in as: {signed_in}" if signed_in else "Not signed in"
        )
        self.google_status_lbl.add_css_class("date-label")
        self.google_status_lbl.set_halign(Gtk.Align.START)
        self.google_status_lbl.set_hexpand(True)

        signin_btn = Gtk.Button(label="🔑 Sign in / Switch account")
        signin_btn.add_css_class("sermon-btn")
        signin_btn.connect("clicked", lambda b: self._google_signin(dialog, box, cal_header))

        signout_btn = Gtk.Button(label="Sign out")
        signout_btn.add_css_class("sermon-btn")
        signout_btn.connect("clicked", lambda b: self._google_signout())

        google_row.append(self.google_status_lbl)
        google_row.append(signin_btn)
        google_row.append(signout_btn)
        box.append(google_row)

        # Font size row
        font_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        font_lbl = Gtk.Label(label="Reading font size:")
        font_lbl.set_hexpand(True)
        font_lbl.set_halign(Gtk.Align.START)
        spin = Gtk.SpinButton()
        spin.set_range(9, 24)
        spin.set_increments(1, 2)
        spin.set_value(self.font_size)
        spin.set_digits(0)
        font_row.append(font_lbl)
        font_row.append(spin)
        box.append(font_row)

        # Theme row
        theme_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        theme_lbl = Gtk.Label(label="Theme:")
        theme_lbl.set_hexpand(True)
        theme_lbl.set_halign(Gtk.Align.START)
        theme_combo = Gtk.DropDown.new_from_strings(["Dark", "Light"])
        theme_combo.set_selected(0 if self.theme == "dark" else 1)
        theme_row.append(theme_lbl)
        theme_row.append(theme_combo)
        box.append(theme_row)

        # Weather location search
        loc_header = Gtk.Label(label="WEATHER LOCATION")
        loc_header.add_css_class("source-label")
        loc_header.set_halign(Gtk.Align.START)
        box.append(loc_header)

        # Current location display
        current_loc_lbl = Gtk.Label(
            label=f"Current: {self.weather_location or 'Auto-detect'}"
        )
        current_loc_lbl.add_css_class("date-label")
        current_loc_lbl.set_halign(Gtk.Align.START)
        box.append(current_loc_lbl)

        # Search row
        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        loc_entry = Gtk.Entry()
        loc_entry.set_placeholder_text("Type a town or city to search…")
        loc_entry.set_hexpand(True)
        search_btn = Gtk.Button(label="Search")
        search_btn.add_css_class("sermon-btn")
        search_row.append(loc_entry)
        search_row.append(search_btn)
        box.append(search_row)

        # Results will appear here
        loc_results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(loc_results_box)

        # Store selected location data
        selected_location = {"name": self.weather_location, "lat": None, "lon": None}

        def do_search(btn=None):
            query = loc_entry.get_text().strip()
            if not query:
                return
            # Clear previous results
            child = loc_results_box.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                loc_results_box.remove(child)
                child = nxt
            loading = Gtk.Label(label="Searching…")
            loading.add_css_class("date-label")
            loc_results_box.append(loading)

            def fetch():
                try:
                    r = requests.get(
                        f"https://geocoding-api.open-meteo.com/v1/search"
                        f"?name={requests.utils.quote(query)}&count=10&language=en&format=json",
                        timeout=5
                    ).json()
                    results = r.get("results", [])
                    GLib.idle_add(show_results, results)
                except Exception as e:
                    GLib.idle_add(show_results, [])

            threading.Thread(target=fetch, daemon=True).start()

        def show_results(results):
            child = loc_results_box.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                loc_results_box.remove(child)
                child = nxt

            if not results:
                lbl = Gtk.Label(label="No results found.")
                lbl.add_css_class("date-label")
                loc_results_box.append(lbl)
                return

            for r in results:
                name  = r.get("name", "")
                admin = r.get("admin1", "")
                country = r.get("country", "")
                lat   = r["latitude"]
                lon   = r["longitude"]
                label = f"{name}, {admin}, {country}" if admin else f"{name}, {country}"
                btn = Gtk.Button(label=label)
                btn.add_css_class("sermon-list-item")
                btn.set_halign(Gtk.Align.FILL)
                def on_pick(b, n=name, lbl=label, la=lat, lo=lon):
                    selected_location["name"] = n
                    selected_location["lat"]  = la
                    selected_location["lon"]  = lo
                    current_loc_lbl.set_text(f"Current: {lbl}")
                    # Clear results
                    c = loc_results_box.get_first_child()
                    while c:
                        nx = c.get_next_sibling()
                        loc_results_box.remove(c)
                        c = nx
                btn.connect("clicked", on_pick)
                loc_results_box.append(btn)

        search_btn.connect("clicked", do_search)
        loc_entry.connect("activate", do_search)

        # Auto-detect option
        auto_btn = Gtk.Button(label="Use auto-detect (IP location)")
        auto_btn.add_css_class("sermon-btn")
        def on_auto(b):
            selected_location["name"] = ""
            selected_location["lat"]  = None
            selected_location["lon"]  = None
            current_loc_lbl.set_text("Current: Auto-detect")
        auto_btn.connect("clicked", on_auto)
        box.append(auto_btn)

        # Calendar selection
        cal_header = Gtk.Label(label="CALENDARS TO SHOW")
        cal_header.add_css_class("source-label")
        cal_header.set_halign(Gtk.Align.START)
        box.append(cal_header)

        cal_note = Gtk.Label(label="Loading calendars…")
        cal_note.add_css_class("date-label")
        cal_note.set_halign(Gtk.Align.START)
        box.append(cal_note)

        # Store checkboxes keyed by calendar ID
        cal_checks = {}

        def load_cals():
            cals = fetch_calendar_list()
            GLib.idle_add(populate_cals, cals)

        def populate_cals(cals):
            box.remove(cal_note)
            if not cals:
                lbl = Gtk.Label(label="Sign in to Google to load calendars.")
                lbl.add_css_class("date-label")
                lbl.set_halign(Gtk.Align.START)
                box.insert_child_after(lbl, cal_header)
                return
            for cal_id, cal_name in cals:
                check = Gtk.CheckButton(label=cal_name)
                active = (not self.enabled_calendars or
                          cal_id in self.enabled_calendars)
                check.set_active(active)
                cal_checks[cal_id] = check
                box.append(check)

        threading.Thread(target=load_cals, daemon=True).start()

        # Buttons
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda b: dialog.close())
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", lambda b: self._save_prefs(
            int(spin.get_value()),
            "dark" if theme_combo.get_selected() == 0 else "light",
            selected_location["name"],
            selected_location.get("lat"),
            selected_location.get("lon"),
            [cal_id for cal_id, check in cal_checks.items() if check.get_active()],
            dialog
        ))
        btn_row.append(cancel_btn)
        btn_row.append(save_btn)
        box.append(btn_row)

        outer.set_child(box)
        dialog.set_child(outer)
        dialog.present()

    def _save_prefs(self, font_size, theme, weather_location, weather_lat, weather_lon, enabled_calendars, dialog):
        self.font_size = font_size
        self.theme = theme
        self.weather_location = weather_location
        self.weather_lat = weather_lat
        self.weather_lon = weather_lon
        self.enabled_calendars = enabled_calendars
        self.prefs.update({
            "font_size": font_size,
            "theme": theme,
            "weather_location": weather_location,
            "weather_lat": weather_lat,
            "weather_lon": weather_lon,
            "enabled_calendars": enabled_calendars,
        })
        save_prefs(self.prefs)
        self._apply_css()
        # Force GTK to re-render all widgets with new styles
        self.queue_draw()
        child = self.get_child()
        if child:
            child.queue_draw()
        threading.Thread(target=self._load_weather, daemon=True).start()
        threading.Thread(target=self._load_calendar, daemon=True).start()
        dialog.close()

    # ── Spurgeon Tab ──────────────────────────────────────────────────────────

    def _build_spurgeon_tab(self):
        self._spurgeon_date = datetime.date.today()

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("tab-content")
        box.set_spacing(8)

        # Header row with title and navigation
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.add_css_class("sermon-toolbar")

        prev_btn = Gtk.Button(label="◀ Prev")
        prev_btn.add_css_class("sermon-btn")
        prev_btn.connect("clicked", self._spurgeon_prev)
        toolbar.append(prev_btn)

        self.spurgeon_date_label = Gtk.Label(
            label=datetime.date.today().strftime("%A, %d %B %Y")
        )
        self.spurgeon_date_label.add_css_class("section-title")
        self.spurgeon_date_label.set_hexpand(True)
        self.spurgeon_date_label.set_halign(Gtk.Align.CENTER)
        toolbar.append(self.spurgeon_date_label)

        next_btn = Gtk.Button(label="Next ▶")
        next_btn.add_css_class("sermon-btn")
        next_btn.connect("clicked", self._spurgeon_next)
        toolbar.append(next_btn)

        today_btn = Gtk.Button(label="Today")
        today_btn.add_css_class("sermon-btn")
        today_btn.connect("clicked", self._spurgeon_today)
        toolbar.append(today_btn)

        box.append(toolbar)

        self.spurgeon_buffer = Gtk.TextBuffer()
        self.spurgeon_buffer.create_tag("bold", weight=Pango.Weight.BOLD)
        self.spurgeon_buffer.create_tag("heading", weight=Pango.Weight.BOLD,
                                        scale=1.2)
        self.spurgeon_buffer.create_tag("normal")

        self.spurgeon_view = Gtk.TextView(buffer=self.spurgeon_buffer)
        self.spurgeon_view.set_editable(False)
        self.spurgeon_view.set_cursor_visible(False)
        self.spurgeon_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.spurgeon_view.set_left_margin(12)
        self.spurgeon_view.set_right_margin(12)
        self.spurgeon_view.set_top_margin(10)
        self.spurgeon_view.set_bottom_margin(10)
        self.spurgeon_view.add_css_class("reading-text")
        self.spurgeon_buffer.set_text("Loading today's reading…")

        box.append(self.spurgeon_view)
        scroll.set_child(box)
        self.notebook.append_page(scroll, Gtk.Label(label="📖 Devotional"))

        threading.Thread(target=self._load_spurgeon, daemon=True).start()

    def _spurgeon_prev(self, btn):
        self._spurgeon_date -= datetime.timedelta(days=1)
        self._spurgeon_refresh()

    def _spurgeon_next(self, btn):
        self._spurgeon_date += datetime.timedelta(days=1)
        self._spurgeon_refresh()

    def _spurgeon_today(self, btn):
        self._spurgeon_date = datetime.date.today()
        self._spurgeon_refresh()

    def _spurgeon_refresh(self):
        self.spurgeon_date_label.set_text(
            self._spurgeon_date.strftime("%A, %d %B %Y")
        )
        self.spurgeon_buffer.set_text("Loading…")
        threading.Thread(target=self._load_spurgeon, daemon=True).start()

    def _load_spurgeon(self):
        text = fetch_spurgeon(self._spurgeon_date)
        GLib.idle_add(self._set_spurgeon, text)

    def _set_spurgeon(self, text):
        import re
        self.spurgeon_buffer.set_text("")
        sections = text.split("\n\n─────────────────────────────────\n\n")
        for i, section in enumerate(sections):
            if i > 0:
                end = self.spurgeon_buffer.get_end_iter()
                self.spurgeon_buffer.insert_with_tags_by_name(
                    end, "\n\n" + "─" * 40 + "\n\n", "bold"
                )
            lines = section.split("\n", 1)
            end = self.spurgeon_buffer.get_end_iter()
            # Bold the heading (☀️ Morning / 🌙 Evening)
            if lines:
                self.spurgeon_buffer.insert_with_tags_by_name(
                    end, lines[0] + "\n\n", "heading"
                )
            if len(lines) > 1:
                body = lines[1].strip()
                # Remove junk header lines from the website
                body = re.sub(
                    r'^(Meditation for.*?Spurgeon\s*)', '', body,
                    flags=re.DOTALL | re.IGNORECASE
                ).strip()
                # Find and bold the date line (e.g. "Saturday, May 02, 2026")
                date_match = re.match(
                    r'^(\w+,\s+\w+\s+\d+,\s+\d{4})(.*)', body, re.DOTALL
                )
                end = self.spurgeon_buffer.get_end_iter()
                if date_match:
                    self.spurgeon_buffer.insert_with_tags_by_name(
                        end, date_match.group(1) + "\n\n", "bold"
                    )
                    rest = date_match.group(2).strip()
                    # Bold the verse reference (first line of rest)
                    verse_end = rest.find("\n")
                    end = self.spurgeon_buffer.get_end_iter()
                    if verse_end > 0:
                        self.spurgeon_buffer.insert_with_tags_by_name(
                            end, rest[:verse_end] + "\n\n", "bold"
                        )
                        end = self.spurgeon_buffer.get_end_iter()
                        self.spurgeon_buffer.insert_with_tags_by_name(
                            end, rest[verse_end:].strip(), "normal"
                        )
                    else:
                        self.spurgeon_buffer.insert_with_tags_by_name(
                            end, rest, "normal"
                        )
                else:
                    self.spurgeon_buffer.insert_with_tags_by_name(
                        end, body, "normal"
                    )

    # ── News Tab ──────────────────────────────────────────────────────────────

    def _build_news_tab(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.news_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.news_box.add_css_class("tab-content")
        self.news_box.set_spacing(2)

        loading = Gtk.Label(label="Loading news…")
        loading.add_css_class("status-label")
        self.news_box.append(loading)

        scroll.set_child(self.news_box)
        self.notebook.append_page(scroll, Gtk.Label(label="📰 News"))

        threading.Thread(target=self._load_news, daemon=True).start()

    def _load_news(self):
        all_items = {}
        for source, url in NEWS_SOURCES.items():
            all_items[source] = fetch_news(url)
        GLib.idle_add(self._set_news, all_items)

    def _set_news(self, all_items):
        # Clear loading label
        child = self.news_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.news_box.remove(child)
            child = next_child

        for source, items in all_items.items():
            src_lbl = Gtk.Label(label=source.upper())
            src_lbl.add_css_class("source-label")
            src_lbl.set_halign(Gtk.Align.START)
            self.news_box.append(src_lbl)

            for title, link in items:
                btn = Gtk.Button(label=f"  • {title}")
                btn.add_css_class("news-button")
                btn.set_halign(Gtk.Align.FILL)
                if link:
                    btn.connect("clicked", self._open_link, link)
                self.news_box.append(btn)

    def _open_link(self, btn, url):
        import subprocess
        subprocess.Popen(["xdg-open", url])

    # ── Weather Tab ───────────────────────────────────────────────────────────

    def _build_weather_tab(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.weather_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.weather_outer.add_css_class("tab-content")
        self.weather_outer.set_spacing(16)

        # Current conditions box
        current_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        current_box.add_css_class("weather-box")
        current_box.set_spacing(6)
        current_box.set_halign(Gtk.Align.CENTER)

        self.weather_temp = Gtk.Label(label="--°C")
        self.weather_temp.add_css_class("weather-temp")
        current_box.append(self.weather_temp)

        self.weather_desc = Gtk.Label(label="Loading weather…")
        self.weather_desc.add_css_class("weather-desc")
        current_box.append(self.weather_desc)

        self.weather_outer.append(current_box)

        # 7-day forecast header
        forecast_title = Gtk.Label(label="7-DAY FORECAST")
        forecast_title.add_css_class("source-label")
        forecast_title.set_halign(Gtk.Align.START)
        self.weather_outer.append(forecast_title)

        # Forecast grid — will be populated after data loads
        self.forecast_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.forecast_box.set_spacing(4)
        self.weather_outer.append(self.forecast_box)

        note = Gtk.Label(label="Weather powered by Open-Meteo (no API key needed)")
        note.add_css_class("date-label")
        note.set_halign(Gtk.Align.CENTER)
        self.weather_outer.append(note)

        scroll.set_child(self.weather_outer)
        self.notebook.append_page(scroll, Gtk.Label(label="🌤️ Weather"))
        threading.Thread(target=self._load_weather, daemon=True).start()

    def _load_weather(self):
        try:
            location = self.weather_location.strip()
            if self.weather_lat and self.weather_lon:
                # Use pinned coordinates directly — no geocoding needed
                lat  = self.weather_lat
                lon  = self.weather_lon
                city = self.weather_location or "Your location"
            elif location:
                geo = requests.get(
                    f"https://geocoding-api.open-meteo.com/v1/search"
                    f"?name={requests.utils.quote(location)}&count=1&language=en&format=json",
                    timeout=5
                ).json()
                results = geo.get("results", [])
                if not results:
                    GLib.idle_add(self._set_weather, "--°C",
                                  f"Location not found: {location}", [])
                    return
                best = results[0]
                lat  = best["latitude"]
                lon  = best["longitude"]
                city = best.get("name", location)
            else:
                loc  = requests.get("https://ipapi.co/json/", timeout=5).json()
                lat  = loc["latitude"]
                lon  = loc["longitude"]
                city = loc.get("city", "Your location")

            # Fetch current + 7-day daily forecast
            w = requests.get(
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&current_weather=true"
                f"&daily=weathercode,temperature_2m_max,temperature_2m_min"
                f"&temperature_unit=celsius&timezone=auto",
                timeout=5
            ).json()

            temp = w["current_weather"]["temperature"]
            code = w["current_weather"]["weathercode"]
            desc = self._weather_code(code)
            current_str = f"{desc}  —  {city}"

            # Build 7-day list
            daily = w.get("daily", {})
            dates   = daily.get("time", [])
            codes   = daily.get("weathercode", [])
            maxtemps = daily.get("temperature_2m_max", [])
            mintemps = daily.get("temperature_2m_min", [])

            forecast = []
            for i in range(min(7, len(dates))):
                date_obj = datetime.date.fromisoformat(dates[i])
                day_name = date_obj.strftime("%A")
                icon     = self._weather_code(codes[i]).split()[0] if codes else "?"
                hi       = f"{maxtemps[i]:.0f}°" if maxtemps else "--"
                lo       = f"{mintemps[i]:.0f}°" if mintemps else "--"
                forecast.append((day_name, icon, hi, lo))

            GLib.idle_add(self._set_weather, f"{temp}°C", current_str, forecast)
        except Exception as e:
            GLib.idle_add(self._set_weather, "--°C",
                          f"Could not load weather: {e}", [])

    def _set_weather(self, temp, desc, forecast):
        self.weather_temp.set_text(temp)
        self.weather_desc.set_text(desc)

        # Clear old forecast rows
        child = self.forecast_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.forecast_box.remove(child)
            child = nxt

        # Add new forecast rows
        for day_name, icon, hi, lo in forecast:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.add_css_class("forecast-row")

            day_lbl = Gtk.Label(label=day_name)
            day_lbl.add_css_class("forecast-day")
            day_lbl.set_width_chars(12)
            day_lbl.set_halign(Gtk.Align.START)

            icon_lbl = Gtk.Label(label=icon)
            icon_lbl.set_width_chars(4)

            hi_lbl = Gtk.Label(label=f"↑ {hi}")
            hi_lbl.add_css_class("forecast-hi")
            hi_lbl.set_width_chars(7)

            lo_lbl = Gtk.Label(label=f"↓ {lo}")
            lo_lbl.add_css_class("forecast-lo")

            row.append(day_lbl)
            row.append(icon_lbl)
            row.append(hi_lbl)
            row.append(lo_lbl)
            self.forecast_box.append(row)

    def _weather_code(self, code):
        codes = {
            0: "Clear sky ☀️", 1: "Mainly clear 🌤️", 2: "Partly cloudy ⛅",
            3: "Overcast ☁️", 45: "Foggy 🌫️", 48: "Icy fog 🌫️",
            51: "Light drizzle 🌦️", 53: "Drizzle 🌦️", 55: "Heavy drizzle 🌧️",
            61: "Light rain 🌧️", 63: "Rain 🌧️", 65: "Heavy rain 🌧️",
            71: "Light snow ❄️", 73: "Snow ❄️", 75: "Heavy snow ❄️",
            80: "Showers 🌦️", 81: "Showers 🌦️", 82: "Heavy showers 🌧️",
            95: "Thunderstorm ⛈️", 96: "Thunderstorm ⛈️", 99: "Thunderstorm ⛈️",
        }
        return codes.get(code, f"Weather code {code}")


    # ── Sermon Notes Tab ──────────────────────────────────────────────────────

    def _build_sermon_tab(self):
        SERMONS_DIR = os.path.expanduser("~/morning-dashboard/sermons")
        os.makedirs(SERMONS_DIR, exist_ok=True)
        self.sermons_dir = SERMONS_DIR
        self.current_sermon_file = None

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        outer.add_css_class("tab-content")
        outer.set_spacing(12)

        # ── Left panel: sermon list ──────────────────────────────────────────
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_size_request(200, -1)

        list_title = Gtk.Label(label="MY SERMONS")
        list_title.add_css_class("source-label")
        list_title.set_halign(Gtk.Align.START)
        left.append(list_title)

        new_btn = Gtk.Button(label="＋ New Sermon")
        new_btn.add_css_class("sermon-btn")
        new_btn.connect("clicked", self._new_sermon)
        left.append(new_btn)

        scroll_list = Gtk.ScrolledWindow()
        scroll_list.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll_list.set_vexpand(True)

        self.sermon_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scroll_list.set_child(self.sermon_list_box)
        left.append(scroll_list)

        # ── Right panel: editor ──────────────────────────────────────────────
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_hexpand(True)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.add_css_class("sermon-toolbar")

        self.sermon_title_entry = Gtk.Entry()
        self.sermon_title_entry.set_placeholder_text("Sermon title…")
        self.sermon_title_entry.add_css_class("sermon-title-entry")
        self.sermon_title_entry.set_hexpand(True)
        toolbar.append(self.sermon_title_entry)

        save_btn = Gtk.Button(label="💾 Save")
        save_btn.add_css_class("sermon-btn")
        save_btn.connect("clicked", self._save_sermon)
        toolbar.append(save_btn)

        delete_btn = Gtk.Button(label="🗑 Delete")
        delete_btn.add_css_class("sermon-btn")
        delete_btn.connect("clicked", self._delete_sermon)
        toolbar.append(delete_btn)

        sync_btn = Gtk.Button(label="☁️ Sync to Drive")
        sync_btn.add_css_class("sermon-btn")
        sync_btn.connect("clicked", self._sync_to_drive)
        toolbar.append(sync_btn)

        right.append(toolbar)

        # Sync status label
        self.sync_status = Gtk.Label(label="")
        self.sync_status.add_css_class("date-label")
        self.sync_status.set_halign(Gtk.Align.START)
        right.append(self.sync_status)

        # Text editor
        scroll_text = Gtk.ScrolledWindow()
        scroll_text.set_vexpand(True)
        scroll_text.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.sermon_buffer = Gtk.TextBuffer()
        self.sermon_view = Gtk.TextView(buffer=self.sermon_buffer)
        self.sermon_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.sermon_view.set_left_margin(12)
        self.sermon_view.set_right_margin(12)
        self.sermon_view.set_top_margin(10)
        self.sermon_view.set_bottom_margin(10)
        self.sermon_view.add_css_class("reading-text")

        scroll_text.set_child(self.sermon_view)
        right.append(scroll_text)

        outer.append(left)
        outer.append(right)

        self.notebook.append_page(outer, Gtk.Label(label="✍️ Sermons"))
        self._refresh_sermon_list()

    def _refresh_sermon_list(self):
        # Clear list
        child = self.sermon_list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.sermon_list_box.remove(child)
            child = nxt

        files = sorted([
            f for f in os.listdir(self.sermons_dir) if f.endswith(".txt")
        ])
        for fname in files:
            btn = Gtk.Button(label=fname[:-4])  # strip .txt
            btn.add_css_class("sermon-list-item")
            btn.set_halign(Gtk.Align.FILL)
            btn.connect("clicked", self._load_sermon, fname)
            self.sermon_list_box.append(btn)

    def _new_sermon(self, btn):
        self.current_sermon_file = None
        self.sermon_title_entry.set_text("")
        self.sermon_buffer.set_text("")
        self.sermon_title_entry.grab_focus()

    def _save_sermon(self, btn):
        title = self.sermon_title_entry.get_text().strip()
        if not title:
            self.sermon_title_entry.set_placeholder_text("Please enter a title first!")
            return
        start = self.sermon_buffer.get_start_iter()
        end   = self.sermon_buffer.get_end_iter()
        text  = self.sermon_buffer.get_text(start, end, True)
        fname = title.replace("/", "-") + ".txt"
        fpath = os.path.join(self.sermons_dir, fname)
        with open(fpath, "w") as f:
            f.write(text)
        self.current_sermon_file = fname
        self._refresh_sermon_list()

    def _load_sermon(self, btn, fname):
        fpath = os.path.join(self.sermons_dir, fname)
        try:
            with open(fpath) as f:
                text = f.read()
            self.sermon_title_entry.set_text(fname[:-4])
            self.sermon_buffer.set_text(text)
            self.current_sermon_file = fname
        except Exception as e:
            self.sermon_buffer.set_text(f"Error loading file: {e}")

    def _delete_sermon(self, btn):
        if not self.current_sermon_file:
            return
        fpath = os.path.join(self.sermons_dir, self.current_sermon_file)
        try:
            os.remove(fpath)
        except Exception:
            pass
        self.current_sermon_file = None
        self.sermon_title_entry.set_text("")
        self.sermon_buffer.set_text("")
        self._refresh_sermon_list()


    # ── Calendar Tab ──────────────────────────────────────────────────────────

    def _build_calendar_tab(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)

        self.cal_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.cal_box.add_css_class("tab-content")
        self.cal_box.set_spacing(4)
        self.cal_box.set_hexpand(False)
        self.cal_box.set_size_request(400, -1)

        # Header row
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title = Gtk.Label(label="📅  Upcoming Events")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)

        refresh_btn = Gtk.Button(label="🔄 Refresh")
        refresh_btn.add_css_class("sermon-btn")
        refresh_btn.connect("clicked", lambda b: self._load_calendar())
        header_row.append(title)
        header_row.append(refresh_btn)
        self.cal_box.append(header_row)

        self.cal_status = Gtk.Label(label="Loading calendar…")
        self.cal_status.add_css_class("status-label")
        self.cal_status.set_halign(Gtk.Align.START)
        self.cal_status.set_wrap(True)
        self.cal_status.set_wrap_mode(Pango.WrapMode.WORD)
        self.cal_status.set_max_width_chars(80)
        self.cal_box.append(self.cal_status)

        scroll.set_child(self.cal_box)
        self.notebook.append_page(scroll, Gtk.Label(label="📅 Calendar"))
        threading.Thread(target=self._load_calendar, daemon=True).start()

    def _load_calendar(self):
        if not os.path.exists(CREDENTIALS):
            GLib.idle_add(self._set_calendar,
                          [("", "credentials.json not found — please set up Google API", "", "", "")])
            return
        enabled = self.enabled_calendars if self.enabled_calendars else None
        events = fetch_calendar_events(enabled)
        GLib.idle_add(self._set_calendar, events)

    def _set_calendar(self, events):
        # Remove everything after the header row and status label
        children = []
        child = self.cal_box.get_first_child()
        while child:
            children.append(child)
            child = child.get_next_sibling()
        for c in children[2:]:
            self.cal_box.remove(c)

        if not events:
            self.cal_status.set_text("No events in the next 7 days.")
            return

        if events[0][1] == "Error":
            self.cal_status.set_text(f"❌ {events[0][3]}")
            return

        self.cal_status.set_text("")

        # Group by day
        from itertools import groupby
        for day_str, day_events in groupby(events, key=lambda x: x[1]):
            hdr = Gtk.Label(label=day_str.upper())
            hdr.add_css_class("cal-day-header")
            hdr.set_halign(Gtk.Align.START)
            self.cal_box.append(hdr)

            for _, _, time_str, summary, cal_name in day_events:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
                row.add_css_class("cal-event-row")

                time_lbl = Gtk.Label(label=time_str)
                time_lbl.add_css_class("cal-event-time")
                time_lbl.set_halign(Gtk.Align.START)
                time_lbl.set_width_chars(8)

                title_lbl = Gtk.Label(label=summary)
                title_lbl.add_css_class("cal-event-title")
                title_lbl.set_halign(Gtk.Align.START)
                title_lbl.set_hexpand(True)
                title_lbl.set_wrap(True)
                title_lbl.set_wrap_mode(Pango.WrapMode.WORD)
                title_lbl.set_max_width_chars(50)

                cal_lbl = Gtk.Label(label=cal_name)
                cal_lbl.add_css_class("cal-event-time")
                cal_lbl.set_halign(Gtk.Align.END)

                row.append(time_lbl)
                row.append(title_lbl)
                row.append(cal_lbl)
                self.cal_box.append(row)

    def _sync_to_drive(self, btn):
        if not os.path.exists(CREDENTIALS):
            self.sync_status.set_text("❌ credentials.json not found in ~/morning-dashboard/")
            return
        self.sync_status.set_text("Starting sync…")
        def run():
            sync_sermons_to_drive(
                self.sermons_dir,
                lambda msg: GLib.idle_add(self.sync_status.set_text, msg)
            )
        threading.Thread(target=run, daemon=True).start()

    # ── Bible Tab ─────────────────────────────────────────────────────────────

    def _build_bible_tab(self):
        self._bible_book_idx    = 0
        self._bible_chapter     = 1
        self._bible_translation = 0  # index into BIBLE_TRANSLATIONS

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("tab-content")
        outer.set_spacing(8)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.add_css_class("sermon-toolbar")

        # Translation dropdown
        trans_names = [t[0] for t in BIBLE_TRANSLATIONS]
        self.bible_trans_combo = Gtk.DropDown.new_from_strings(trans_names)
        self.bible_trans_combo.set_selected(0)
        toolbar.append(self.bible_trans_combo)

        # Book dropdown
        book_names = [b[0] for b in BIBLE_BOOKS]
        self.bible_book_combo = Gtk.DropDown.new_from_strings(book_names)
        self.bible_book_combo.set_selected(0)
        self.bible_book_combo.connect("notify::selected", self._on_bible_book_changed)
        toolbar.append(self.bible_book_combo)

        # Chapter spinner
        self.bible_chapter_spin = Gtk.SpinButton()
        self.bible_chapter_spin.set_range(1, BIBLE_BOOKS[0][2])
        self.bible_chapter_spin.set_increments(1, 5)
        self.bible_chapter_spin.set_value(1)
        self.bible_chapter_spin.set_digits(0)
        self.bible_chapter_spin.set_width_chars(4)
        toolbar.append(self.bible_chapter_spin)

        go_btn = Gtk.Button(label="Go")
        go_btn.add_css_class("sermon-btn")
        go_btn.connect("clicked", self._load_bible_chapter)
        toolbar.append(go_btn)

        prev_btn = Gtk.Button(label="◀ Prev")
        prev_btn.add_css_class("sermon-btn")
        prev_btn.connect("clicked", self._bible_prev)
        toolbar.append(prev_btn)

        next_btn = Gtk.Button(label="Next ▶")
        next_btn.add_css_class("sermon-btn")
        next_btn.connect("clicked", self._bible_next)
        toolbar.append(next_btn)

        self.bible_ref_label = Gtk.Label(label="")
        self.bible_ref_label.add_css_class("section-title")
        self.bible_ref_label.set_halign(Gtk.Align.END)
        self.bible_ref_label.set_hexpand(True)
        toolbar.append(self.bible_ref_label)

        outer.append(toolbar)

        # ── Text area ─────────────────────────────────────────────────────────
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self.bible_buffer = Gtk.TextBuffer()
        self.bible_view = Gtk.TextView(buffer=self.bible_buffer)
        self.bible_view.set_editable(False)
        self.bible_view.set_cursor_visible(False)
        self.bible_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.bible_view.set_left_margin(12)
        self.bible_view.set_right_margin(12)
        self.bible_view.set_top_margin(10)
        self.bible_view.set_bottom_margin(10)
        self.bible_view.add_css_class("bible-verse")

        self.bible_buffer.set_text("Select a book and chapter above.")

        scroll.set_child(self.bible_view)
        outer.append(scroll)

        self.notebook.append_page(outer, Gtk.Label(label="📜 Bible"))

        # Load Genesis 1 by default
        self._do_load_bible(0, 1)

    def _on_bible_book_changed(self, combo, _):
        idx = combo.get_selected()
        max_ch = BIBLE_BOOKS[idx][2]
        self.bible_chapter_spin.set_range(1, max_ch)
        self.bible_chapter_spin.set_value(1)

    def _load_bible_chapter(self, btn=None):
        idx = self.bible_book_combo.get_selected()
        ch  = int(self.bible_chapter_spin.get_value())
        self._do_load_bible(idx, ch)

    def _do_load_bible(self, book_idx, chapter):
        self._bible_book_idx = book_idx
        self._bible_chapter  = chapter
        trans_idx = self.bible_trans_combo.get_selected()
        self._bible_translation = trans_idx
        book_name, book_id, max_ch = BIBLE_BOOKS[book_idx]
        trans_name = BIBLE_TRANSLATIONS[trans_idx][0]
        trans_id   = BIBLE_TRANSLATIONS[trans_idx][1]
        self.bible_ref_label.set_text(f"{book_name} {chapter}  —  {trans_name}")
        self.bible_buffer.set_text("Loading…")
        threading.Thread(
            target=self._fetch_and_set_bible,
            args=(book_id, chapter, trans_id),
            daemon=True
        ).start()

    def _fetch_and_set_bible(self, book_id, chapter, trans_id):
        text = fetch_esv_chapter(book_id, chapter, trans_id)
        GLib.idle_add(self._set_bible_text, text)

    def _set_bible_text(self, text):
        self.bible_buffer.set_text(text)

    def _bible_prev(self, btn):
        ch  = self._bible_chapter
        idx = self._bible_book_idx
        if ch > 1:
            self._do_load_bible(idx, ch - 1)
            self.bible_chapter_spin.set_value(ch - 1)
        elif idx > 0:
            new_idx = idx - 1
            new_ch  = BIBLE_BOOKS[new_idx][2]
            self.bible_book_combo.set_selected(new_idx)
            self.bible_chapter_spin.set_value(new_ch)
            self._do_load_bible(new_idx, new_ch)

    def _bible_next(self, btn):
        ch      = self._bible_chapter
        idx     = self._bible_book_idx
        max_ch  = BIBLE_BOOKS[idx][2]
        if ch < max_ch:
            self._do_load_bible(idx, ch + 1)
            self.bible_chapter_spin.set_value(ch + 1)
        elif idx < len(BIBLE_BOOKS) - 1:
            new_idx = idx + 1
            self.bible_book_combo.set_selected(new_idx)
            self.bible_chapter_spin.set_value(1)
            self._do_load_bible(new_idx, 1)

    # ── Prayer List Tab ───────────────────────────────────────────────────────

    def _build_prayer_tab(self):
        PRAYER_FILE = os.path.expanduser("~/morning-dashboard/prayers.json")
        self.prayer_file = PRAYER_FILE

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("tab-content")
        outer.set_spacing(8)

        # Header row
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label="🙏  Prayer List")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)

        clear_btn = Gtk.Button(label="✓ Clear prayed")
        clear_btn.add_css_class("sermon-btn")
        clear_btn.connect("clicked", self._prayer_clear_done)
        header_row.append(title)
        header_row.append(clear_btn)
        outer.append(header_row)

        # Add new prayer row
        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add_row.add_css_class("sermon-toolbar")
        self.prayer_entry = Gtk.Entry()
        self.prayer_entry.set_placeholder_text("Add a new prayer request…")
        self.prayer_entry.set_hexpand(True)
        self.prayer_entry.add_css_class("sermon-title-entry")
        self.prayer_entry.connect("activate", self._prayer_add)
        add_btn = Gtk.Button(label="+ Add")
        add_btn.add_css_class("sermon-btn")
        add_btn.connect("clicked", self._prayer_add)
        add_row.append(self.prayer_entry)
        add_row.append(add_btn)
        outer.append(add_row)

        # Scrollable prayer list
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self.prayer_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.set_child(self.prayer_list_box)
        outer.append(scroll)

        self.notebook.append_page(outer, Gtk.Label(label="🙏 Prayer"))
        self._prayer_load()

    def _prayer_load(self):
        """Load prayers from file and render the list."""
        try:
            with open(self.prayer_file) as f:
                self.prayers = json.load(f)
        except Exception:
            self.prayers = []
        self._prayer_render()

    def _prayer_save(self):
        with open(self.prayer_file, "w") as f:
            json.dump(self.prayers, f, indent=2)

    def _prayer_render(self):
        # Clear existing
        child = self.prayer_list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.prayer_list_box.remove(child)
            child = nxt

        # Sort — undone first, done at bottom
        undone = [p for p in self.prayers if not p.get("done")]
        done   = [p for p in self.prayers if p.get("done")]

        for prayer in undone + done:
            self._prayer_add_row(prayer)

    def _prayer_add_row(self, prayer):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        check = Gtk.CheckButton()
        check.set_active(prayer.get("done", False))
        check.connect("toggled", self._prayer_toggle, prayer)

        lbl = Gtk.Label(label=prayer["text"])
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        lbl.set_wrap(True)
        lbl.set_wrap_mode(Pango.WrapMode.WORD)
        lbl.set_xalign(0)
        if prayer.get("done"):
            lbl.add_css_class("prayer-done")
        else:
            lbl.add_css_class("prayer-item")

        del_btn = Gtk.Button(label="✕")
        del_btn.add_css_class("sermon-btn")
        del_btn.connect("clicked", self._prayer_delete, prayer)

        row.append(check)
        row.append(lbl)
        row.append(del_btn)
        self.prayer_list_box.append(row)

    def _prayer_add(self, widget):
        text = self.prayer_entry.get_text().strip()
        if not text:
            return
        self.prayers.append({"text": text, "done": False})
        self.prayer_entry.set_text("")
        self._prayer_save()
        self._prayer_render()

    def _prayer_toggle(self, check, prayer):
        prayer["done"] = check.get_active()
        self._prayer_save()
        self._prayer_render()

    def _prayer_delete(self, btn, prayer):
        self.prayers = [p for p in self.prayers if p is not prayer]
        self._prayer_save()
        self._prayer_render()

    def _prayer_clear_done(self, btn):
        self.prayers = [p for p in self.prayers if not p.get("done")]
        self._prayer_save()
        self._prayer_render()

# ── App entry point ───────────────────────────────────────────────────────────

SETUP_FLAG = os.path.expanduser("~/.config/morning-dashboard/setup_complete")

# ── First-run Setup Wizard ────────────────────────────────────────────────────

class SetupWizard(Gtk.ApplicationWindow):
    def __init__(self, app, on_complete):
        super().__init__(application=app, title="Welcome to Morning Dashboard")
        self.set_default_size(640, 520)
        self.set_resizable(False)
        self.on_complete = on_complete

        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window { background-color: #1a1a2e; }
            .wizard-title {
                font-size: 24px; font-weight: bold;
                color: #f5c842; padding: 8px 0;
            }
            .wizard-sub {
                font-size: 14px; color: #e0e0e0; padding: 4px 0;
            }
            .wizard-body {
                font-size: 13px; color: #a0a0c0; line-height: 1.7;
            }
            .wizard-section {
                font-size: 13px; font-weight: bold;
                color: #e94560; padding-top: 12px;
            }
            .wizard-btn {
                background-color: #e94560; color: #ffffff;
                font-size: 13px; font-weight: bold;
                border: none; border-radius: 8px; padding: 8px 20px;
            }
            .wizard-btn:hover { background-color: #c73050; }
            .wizard-btn-secondary {
                background-color: #0f3460; color: #a0a0c0;
                font-size: 13px; border: none;
                border-radius: 8px; padding: 8px 20px;
            }
            .wizard-btn-secondary:hover { background-color: #16213e; color: #ffffff; }
            .wizard-entry {
                background-color: #16213e; color: #e0e0e0;
                border: 1px solid #0f3460; border-radius: 6px; padding: 6px 10px;
                font-size: 13px;
            }
            .step-dot {
                background-color: #0f3460;
                border-radius: 50%;
            }
            .step-dot-active { background-color: #e94560; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.step = 0
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)

        self._build_step0()  # Welcome
        self._build_step1()  # Core features (no Google needed)
        self._build_step2()  # Google setup (optional)
        self._build_step3()  # Done

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Progress dots
        dots_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        dots_row.set_halign(Gtk.Align.CENTER)
        dots_row.set_margin_top(16)
        self.dots = []
        for i in range(4):
            dot = Gtk.Box()
            dot.set_size_request(10, 10)
            dot.add_css_class("step-dot")
            if i == 0:
                dot.add_css_class("step-dot-active")
            dots_row.append(dot)
            self.dots.append(dot)

        outer.append(dots_row)
        outer.append(self.stack)
        self.set_child(outer)
        self.stack.set_visible_child_name("step0")

    def _make_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(32)
        page.set_margin_bottom(32)
        page.set_margin_start(48)
        page.set_margin_end(48)
        return page

    def _build_step0(self):
        page = self._make_page()
        icon = Gtk.Label(label="☀️")
        icon.set_halign(Gtk.Align.CENTER)

        title = Gtk.Label(label="Welcome to Morning Dashboard")
        title.add_css_class("wizard-title")
        title.set_halign(Gtk.Align.CENTER)
        title.set_wrap(True)

        sub = Gtk.Label(label="Your personal daily briefing for the desktop")
        sub.add_css_class("wizard-sub")
        sub.set_halign(Gtk.Align.CENTER)

        desc = Gtk.Label(
            label="Morning Dashboard brings together everything you need to start "
                  "your day — devotional readings, news, weather, Bible, sermon notes, "
                  "calendar and a prayer list.\n\nThis wizard will get you set up in "
                  "just a few steps."
        )
        desc.add_css_class("wizard-body")
        desc.set_wrap(True)
        desc.set_xalign(0)

        next_btn = Gtk.Button(label="Get Started →")
        next_btn.add_css_class("wizard-btn")
        next_btn.set_halign(Gtk.Align.CENTER)
        next_btn.set_margin_top(16)
        next_btn.connect("clicked", lambda b: self._go_to(1))

        page.append(icon)
        page.append(title)
        page.append(sub)
        page.append(desc)
        page.append(next_btn)
        self.stack.add_named(page, "step0")

    def _build_step1(self):
        page = self._make_page()

        title = Gtk.Label(label="✅  Ready to use — no setup needed")
        title.add_css_class("wizard-title")
        title.set_halign(Gtk.Align.START)
        title.set_wrap(True)

        desc = Gtk.Label(
            label="These features work straight away:"
        )
        desc.add_css_class("wizard-body")
        desc.set_xalign(0)

        features = [
            ("📖", "Spurgeon Morning & Evening devotional"),
            ("📰", "News — BBC, AI & Tech headlines"),
            ("🌤️", "Weather with 7-day forecast"),
            ("📜", "Bible reader — 10 translations, all 66 books"),
            ("🙏", "Prayer list"),
        ]
        for icon, text in features:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_margin_top(4)
            ico = Gtk.Label(label=icon)
            lbl = Gtk.Label(label=text)
            lbl.add_css_class("wizard-sub")
            lbl.set_halign(Gtk.Align.START)
            row.append(ico)
            row.append(lbl)
            page.append(row)

        google_lbl = Gtk.Label(
            label="\nFor Sermon Notes (Drive sync) and Calendar you'll need a "
                  "free Google account setup on the next step — but you can skip "
                  "that and set it up later in Preferences."
        )
        google_lbl.add_css_class("wizard-body")
        google_lbl.set_wrap(True)
        google_lbl.set_xalign(0)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_row.set_halign(Gtk.Align.CENTER)
        btn_row.set_margin_top(16)

        skip_btn = Gtk.Button(label="Skip — start without Google")
        skip_btn.add_css_class("wizard-btn-secondary")
        skip_btn.connect("clicked", lambda b: self._finish())

        next_btn = Gtk.Button(label="Set up Google →")
        next_btn.add_css_class("wizard-btn")
        next_btn.connect("clicked", lambda b: self._go_to(2))

        btn_row.append(skip_btn)
        btn_row.append(next_btn)

        page.append(title)
        page.append(desc)
        page.append(google_lbl)
        page.append(btn_row)
        self.stack.add_named(page, "step1")

    def _build_step2(self):
        page = self._make_page()

        title = Gtk.Label(label="🔑  Google Setup (optional)")
        title.add_css_class("wizard-title")
        title.set_halign(Gtk.Align.START)
        title.set_wrap(True)

        steps_lbl = Gtk.Label(
            label="To enable Calendar and Drive sync you need a free Google Cloud "
                  "credentials file. Here's how to get one:"
        )
        steps_lbl.add_css_class("wizard-body")
        steps_lbl.set_wrap(True)
        steps_lbl.set_xalign(0)

        steps = [
            "1.  Go to console.cloud.google.com",
            "2.  Create a project (or use an existing one)",
            "3.  Enable Google Drive API and Google Calendar API",
            "4.  Go to APIs & Services → Credentials",
            "5.  Create OAuth 2.0 Client ID → Desktop app",
            "6.  Download the JSON file and select it below",
        ]
        for s in steps:
            lbl = Gtk.Label(label=s)
            lbl.add_css_class("wizard-body")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_xalign(0)
            page.append(lbl)

        link_btn = Gtk.Button(label="🌐  Open Google Cloud Console")
        link_btn.add_css_class("wizard-btn-secondary")
        link_btn.set_halign(Gtk.Align.START)
        link_btn.connect("clicked", lambda b: __import__("subprocess").Popen(
            ["xdg-open", "https://console.cloud.google.com"]
        ))

        self.creds_status = Gtk.Label(label="No credentials file selected")
        self.creds_status.add_css_class("wizard-body")
        self.creds_status.set_halign(Gtk.Align.START)

        browse_btn = Gtk.Button(label="📂  Select credentials.json")
        browse_btn.add_css_class("wizard-btn")
        browse_btn.set_halign(Gtk.Align.START)
        browse_btn.connect("clicked", self._browse_credentials)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_row.set_halign(Gtk.Align.CENTER)
        btn_row.set_margin_top(12)

        skip_btn = Gtk.Button(label="Skip for now")
        skip_btn.add_css_class("wizard-btn-secondary")
        skip_btn.connect("clicked", lambda b: self._finish())

        self.google_next_btn = Gtk.Button(label="Continue →")
        self.google_next_btn.add_css_class("wizard-btn")
        self.google_next_btn.set_sensitive(os.path.exists(CREDENTIALS))
        self.google_next_btn.connect("clicked", lambda b: self._go_to(3))

        btn_row.append(skip_btn)
        btn_row.append(self.google_next_btn)

        page.append(title)
        page.append(steps_lbl)
        page.append(link_btn)
        page.append(self.creds_status)
        page.append(browse_btn)
        page.append(btn_row)
        self.stack.add_named(page, "step2")

    def _build_step3(self):
        page = self._make_page()

        icon = Gtk.Label(label="🎉")
        icon.set_halign(Gtk.Align.CENTER)

        title = Gtk.Label(label="All set!")
        title.add_css_class("wizard-title")
        title.set_halign(Gtk.Align.CENTER)

        desc = Gtk.Label(
            label="Morning Dashboard is ready to go.\n\n"
                  "You can customise your weather location, theme, font size "
                  "and calendars at any time from the Preferences button.\n\n"
                  "Enjoy your mornings! ☀️"
        )
        desc.add_css_class("wizard-sub")
        desc.set_wrap(True)
        desc.set_xalign(0)
        desc.set_halign(Gtk.Align.CENTER)

        start_btn = Gtk.Button(label="☀️  Open Morning Dashboard")
        start_btn.add_css_class("wizard-btn")
        start_btn.set_halign(Gtk.Align.CENTER)
        start_btn.set_margin_top(24)
        start_btn.connect("clicked", lambda b: self._finish())

        page.append(icon)
        page.append(title)
        page.append(desc)
        page.append(start_btn)
        self.stack.add_named(page, "step3")

    def _go_to(self, step):
        self.step = step
        for i, dot in enumerate(self.dots):
            if i == step:
                dot.add_css_class("step-dot-active")
            else:
                dot.remove_css_class("step-dot-active")
        self.stack.set_visible_child_name(f"step{step}")

    def _browse_credentials(self, btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Select credentials.json")
        f = Gtk.FileFilter()
        f.set_name("JSON files")
        f.add_pattern("*.json")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(f)
        dialog.set_filters(filters)
        dialog.open(self, None, self._on_credentials_chosen)

    def _on_credentials_chosen(self, dialog, result):
        try:
            from gi.repository import Gio
            file = dialog.open_finish(result)
            if file:
                src = file.get_path()
                import shutil
                os.makedirs(os.path.dirname(CREDENTIALS), exist_ok=True)
                shutil.copy(src, CREDENTIALS)
                self.creds_status.set_text(f"✅  Credentials loaded from {src}")
                self.google_next_btn.set_sensitive(True)
        except Exception as e:
            self.creds_status.set_text(f"❌  Error: {e}")

    def _finish(self):
        # Mark setup as complete
        os.makedirs(os.path.dirname(SETUP_FLAG), exist_ok=True)
        with open(SETUP_FLAG, "w") as f:
            f.write("done")
        self.close()
        self.on_complete()


class DashboardApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.paullintott.morningdashboard")

    def do_activate(self):
        if not os.path.exists(SETUP_FLAG):
            wizard = SetupWizard(self, self._launch_dashboard)
            wizard.present()
        else:
            self._launch_dashboard()

    def _launch_dashboard(self):
        win = MorningDashboard(self)
        win.present()

if __name__ == "__main__":
    app = DashboardApp()
    app.run()
