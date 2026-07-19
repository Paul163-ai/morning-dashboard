#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Pango, Gio, Graphene
import requests
import datetime
import threading
import json
import os
import zipfile
import html as html_lib

# ── Google Drive helper ───────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
PROJECT_DIR    = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS    = os.path.join(PROJECT_DIR, "credentials.json")
TOKEN_FILE     = os.path.join(PROJECT_DIR, "token.json")
DRIVE_FOLDER = "Morning Dashboard Backup"

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

_DATA_FILES = [
    (os.path.expanduser("~/.config/morning-dashboard/spurgeon_notes.json"), "spurgeon_notes.json", "application/json"),
    (os.path.expanduser("~/.config/morning-dashboard/notes.txt"),           "notes.txt",           "text/plain"),
    (os.path.join(PROJECT_DIR, "prayers.json"),                             "prayers.json",        "application/json"),
]

def sync_data_to_drive(status_cb=None):
    """Upload data files to Drive. No-op if not authenticated."""
    def cb(msg):
        if status_cb:
            status_cb(msg)
    if not os.path.exists(TOKEN_FILE):
        cb("❌ Not authenticated — open Google Calendar or Sermon Notes first.")
        return
    try:
        from googleapiclient.http import MediaFileUpload
        service   = get_drive_service()
        folder_id = get_or_create_folder(service, DRIVE_FOLDER)
        q         = f"'{folder_id}' in parents and trashed=false"
        existing  = service.files().list(q=q, fields="files(id,name)").execute()
        existing_map = {f["name"]: f["id"] for f in existing.get("files", [])}
        for local_path, fname, mime in _DATA_FILES:
            if not os.path.exists(local_path):
                continue
            cb(f"Uploading {fname}…")
            media = MediaFileUpload(local_path, mimetype=mime)
            if fname in existing_map:
                service.files().update(fileId=existing_map[fname], media_body=media).execute()
            else:
                meta = {"name": fname, "parents": [folder_id]}
                service.files().create(body=meta, media_body=media, fields="id").execute()
    except Exception as e:
        cb(f"❌ Backup failed: {e}")

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
    ("CSB (API.Bible)", "apibible:CSB"),
    ("NLT (API.Bible)", "apibible:NLT"),
    ("NIV (API.Bible)", "apibible:NIV"),
]

# The seven divisions of the year (plus the Day 365 capstone), from
# web/Systematics/365-outline.md — each entry is the day-of-year its
# division begins on. Kept as a small static list rather than parsed at
# runtime, mirroring the same list in web/static/app.js.
SYSTEMATICS_DIVISIONS = [
    (1,   "The Doctrine of the Word of God"),
    (29,  "The Doctrine of God"),
    (99,  "The Doctrine of Man"),
    (127, "The Doctrines of Christ and the Holy Spirit"),
    (183, "The Application of Redemption"),
    (246, "The Doctrine of the Church"),
    (316, "The Doctrine of the Future"),
    (365, "Capstone"),
]

# Bible IDs on the API.Bible platform (rest.api.bible).
_APIBIBLE_IDS = {
    "CSB": "a556c5305ee15c3f-01",
    "NLT": "d6e14a625393b4da-01",
    "NIV": "3e2eb613d45e131e-01",
}

_APIBIBLE_CITATIONS = {
    "CSB": "Christian Standard Bible® and CSB® are federally registered trademarks of Holman Bible Publishers. All rights reserved. bhpublishinggroup.com",
    "NLT": "Holy Bible, New Living Translation, Copyright © 2014, Tyndale House Publishers. All rights reserved. tyndale.com",
    "NIV": "The Holy Bible, New International Version® NIV® Copyright © 1973, 1978, 1984, 2011 by Biblica, Inc.® Used by Permission of Biblica, Inc.® All rights reserved worldwide.",
}

# Four sequential reading streams for the M'Cheyne daily Bible reading plan.
# Jan 1 starts at: Gen 1 | Ezra 1 | Matt 1 | Acts 1.
MCHEYNE_STREAMS = [
    ["GEN","EXO","LEV","NUM","DEU","JOS","JDG","RUT","1SA","2SA","1KI","2KI",
     "1CH","2CH","EZR","NEH","EST","JOB","PSA","PRO","ECC","SNG","ISA","JER",
     "LAM","EZK","DAN","HOS","JOL","AMO","OBA","JON","MIC","NAH","HAB","ZEP","HAG","ZEC","MAL"],
    ["EZR","NEH","EST","JOB","PSA","PRO","ECC","SNG","ISA","JER","LAM","EZK",
     "DAN","HOS","JOL","AMO","OBA","JON","MIC","NAH","HAB","ZEP","HAG","ZEC","MAL"],
    ["MAT","MRK","LUK","JHN","ACT","ROM","1CO","2CO","GAL","EPH","PHP","COL",
     "1TH","2TH","1TI","2TI","TIT","PHM","HEB","JAS","1PE","2PE","1JN","2JN","3JN","JUD","REV"],
    ["ACT","ROM","1CO","2CO","GAL","EPH","PHP","COL","1TH","2TH","1TI","2TI",
     "TIT","PHM","HEB","JAS","1PE","2PE","1JN","2JN","3JN","JUD","REV","MAT","MRK","LUK","JHN"],
]
_BOOK_ID_TO_INFO = {b[1]: (i, b[2]) for i, b in enumerate(BIBLE_BOOKS)}

def mcheyne_readings_for_date(date=None):
    """Return today's 4 M'Cheyne readings as list of (book_idx, chapter, book_name)."""
    if date is None:
        date = datetime.date.today()
    day = date.timetuple().tm_yday
    results = []
    for stream in MCHEYNE_STREAMS:
        total = sum(_BOOK_ID_TO_INFO[bk][1] for bk in stream)
        pos = (day - 1) % total
        for book_id in stream:
            book_idx, chapters = _BOOK_ID_TO_INFO[book_id]
            if pos < chapters:
                results.append((book_idx, pos + 1, BIBLE_BOOKS[book_idx][0]))
                break
            pos -= chapters
    return results

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

def fetch_apibible_chapter(book_id, chapter, bible_name, api_key):
    """Fetch a chapter from api.scripture.api.bible."""
    import re
    if not api_key:
        return "No API.Bible key set — add one in Preferences."
    bible_id = _APIBIBLE_IDS.get(bible_name)
    if not bible_id:
        return f"Unknown API.Bible translation: {bible_name}"
    try:
        chapter_id = f"{book_id}.{chapter}"
        url = f"https://rest.api.bible/v1/bibles/{bible_id}/chapters/{chapter_id}"
        r = requests.get(
            url,
            headers={"api-key": api_key, "User-Agent": "MorningDashboard/1.0"},
            params={
                "content-type": "text",
                "include-verse-numbers": "true",
                "include-chapter-numbers": "false",
                "include-titles": "false",
                "include-notes": "false",
            },
            timeout=10,
        )
        if r.status_code == 401:
            return "Invalid API.Bible key — check your key in Preferences."
        if r.status_code != 200:
            return f"Could not load chapter (HTTP {r.status_code})"
        content = r.json().get("data", {}).get("content", "")
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", content) if p.strip()]
        return "\n\n".join(paragraphs) if paragraphs else "No text available."
    except Exception as e:
        return f"Error: {e}"

# ── Spurgeon helper ──────────────────────────────────────────────────────────

def fetch_spurgeon(date=None):
    """Fetch Morning & Evening reading from romans45.org archive.

    The reading for a given month/day is the same every year, so results are
    cached locally by month-day to avoid re-scraping on every visit.
    """
    import re
    if date is None:
        date = datetime.date.today()

    month = date.strftime("%m")
    day   = date.strftime("%d")
    cache_key = f"{month}-{day}"

    original_cache = load_spurgeon_original_cache()
    if cache_key in original_cache:
        return "\n\n─────────────────────────────────\n\n".join(
            f"{label}\n\n{text}" for label, text in original_cache[cache_key]
        )

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
                results.append((label, "Reading not found."))
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
                results.append((label, text[:3000]))
            else:
                results.append((label, "Reading not available."))

    except Exception as e:
        return f"Error loading reading: {e}"

    valid = results and not any(
        text in ("Reading not found.", "Reading not available.") for _, text in results
    )
    if valid:
        original_cache[cache_key] = results
        save_spurgeon_original_cache(original_cache)

    return "\n\n─────────────────────────────────\n\n".join(
        f"{label}\n\n{text}" for label, text in results
    )

# ── Spurgeon modernisation (Claude API) ───────────────────────────────────────

def split_spurgeon_sections(combined):
    """Split fetch_spurgeon()'s combined text into (am_text, pm_text), stripping headings."""
    parts = combined.split("\n\n─────────────────────────────────\n\n")
    sections = []
    for part in parts:
        lines = part.split("\n", 1)
        sections.append(lines[1].strip() if len(lines) > 1 else "")
    while len(sections) < 2:
        sections.append("")
    return sections[0], sections[1]

def extract_spurgeon_verse(body):
    """Split a Spurgeon reading body into (quote, reference, reflection).

    Most readings open with '"<verse text>" <Reference>. <reflection>'.
    If that pattern isn't found, returns ("", "", body) unchanged.
    """
    import re
    body = re.sub(
        r'^(Meditation for.*?Spurgeon\s*)', '', body,
        flags=re.DOTALL | re.IGNORECASE
    ).strip()
    ref_m = re.match(
        r'^"([^"]+)"\s+'
        r'((?:\d+\s+)?[A-Z][a-z]+(?:\s+(?:of|the)\s+[A-Z][a-z]+)?'
        r'\s+\d+:\d+[-\d–]*)'
        r'\.\s*(.*)',
        body, re.DOTALL
    )
    if ref_m:
        return ref_m.group(1).strip(), ref_m.group(2).strip(), ref_m.group(3).strip()
    return "", "", body

def build_modernise_prompt(am_reflection, pm_reflection):
    """Build the prompt asking Claude to modernise the two Spurgeon reflections."""
    return (
        "Rewrite the following two devotional reflections by Charles Spurgeon "
        "in clear, modern English, using British English spelling and "
        "conventions. Preserve the meaning and tone. Do not add titles, "
        "headings, commentary, Bible quotations or markdown formatting "
        "— return plain prose only.\n\n"
        "Reply in exactly this format, with no other text:\n"
        "===AM===\n<modernised morning reflection>\n"
        "===PM===\n<modernised evening reflection>\n\n"
        f"=== MORNING REFLECTION ===\n{am_reflection}\n\n"
        f"=== EVENING REFLECTION ===\n{pm_reflection}"
    )

def parse_modernise_reply(reply):
    """Parse a Claude reply in ===AM===/===PM=== format. Returns (am_modern, pm_modern)."""
    import re
    am_match = re.search(r'===AM===\s*(.*?)\s*(?:===PM===|\Z)', reply, re.DOTALL)
    pm_match = re.search(r'===PM===\s*(.*)', reply, re.DOTALL)
    am_modern = am_match.group(1).strip() if am_match else ""
    pm_modern = pm_match.group(1).strip() if pm_match else ""
    return am_modern, pm_modern

def combine_spurgeon_modern(quote, ref, modern):
    """Reassemble a modernised reflection with its verbatim verse + reference."""
    if quote and ref:
        return f'"{quote}" {ref}.\n\n{modern}'
    return modern

def modernize_spurgeon(am_text, pm_text, api_key):
    """Rewrite the AM/PM Spurgeon readings in modern English using the Claude API.

    Returns a dict {"am": ..., "pm": ...} where each value is
    '"<verse>" <Reference>.\\n\\n<modernised reflection>' (verse/reference kept
    verbatim from the original; only the reflection is rewritten). Raises on error.
    """
    am_quote, am_ref, am_reflection = extract_spurgeon_verse(am_text)
    pm_quote, pm_ref, pm_reflection = extract_spurgeon_verse(pm_text)

    prompt = build_modernise_prompt(am_reflection, pm_reflection)

    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Claude API error (HTTP {r.status_code}): {r.text[:300]}")

    data = r.json()
    reply = "".join(b.get("text", "") for b in data.get("content", []))
    am_modern, pm_modern = parse_modernise_reply(reply)

    return {
        "am": combine_spurgeon_modern(am_quote, am_ref, am_modern),
        "pm": combine_spurgeon_modern(pm_quote, pm_ref, pm_modern),
    }

# ── Web URL helper ────────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """Ensure a URL has a scheme and no trailing slash."""
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")

# ── News helper ───────────────────────────────────────────────────────────────

# (name, url, proxy)  proxy=True: fetched via rss2json.com (Cloudflare bypass)
NEWS_SOURCES = [
    ("BBC News",         "https://feeds.bbci.co.uk/news/rss.xml",           False),
    ("Google News",      "https://news.google.com/rss",                      False),
    ("Open Doors",       "https://www.opendoorsuk.org/feed/",                False),
    ("Gospel Coalition", "https://www.thegospelcoalition.org/feed/",         True),
    ("AI News",          "https://feeds.feedburner.com/TheHackersNews",      False),
    ("Tech News",        "https://feeds.bbci.co.uk/news/technology/rss.xml", False),
]

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
                t = html_lib.unescape(t)
                l = link.group(1).strip() if link else ""
                results.append((t, l))
        return results
    except Exception as e:
        return [(f"Error: {e}", "")]

def fetch_news_proxied(url):
    try:
        api = "https://api.rss2json.com/v1/api.json?rss_url=" + requests.utils.quote(url)
        r = requests.get(api, timeout=10, headers={"User-Agent": "MorningDashboard/1.0"})
        data = r.json()
        results = []
        for item in data.get("items", [])[:10]:
            t = item.get("title", "").strip()
            l = item.get("link", "")
            if t:
                results.append((t, l))
        return results or [("No items found", "")]
    except Exception as e:
        return [(f"Error: {e}", "")]

# ── Preferences helpers ───────────────────────────────────────────────────────

PREFS_FILE     = os.path.expanduser("~/.config/morning-dashboard/prefs.json")
AUTOSTART_FILE = os.path.expanduser("~/.config/autostart/morning-dashboard.desktop")
SPURGEON_CACHE_FILE = os.path.expanduser("~/.config/morning-dashboard/spurgeon_cache.json")
SPURGEON_ORIGINAL_CACHE_FILE = os.path.expanduser("~/.config/morning-dashboard/spurgeon_original_cache.json")

ALL_TABS = ["spurgeon", "systematics", "news", "weather", "sermons", "calendar", "bible", "prayer", "notes"]

def load_prefs():
    defaults = {"font_size": 13, "theme": "dark", "weather_location": "", "weather_country": "GB", "enabled_calendars": [], "visible_tabs": ALL_TABS[:], "tab_order": ALL_TABS[:]}
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

def load_spurgeon_cache():
    try:
        with open(SPURGEON_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_spurgeon_cache(cache):
    os.makedirs(os.path.dirname(SPURGEON_CACHE_FILE), exist_ok=True)
    with open(SPURGEON_CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def load_spurgeon_original_cache():
    try:
        with open(SPURGEON_ORIGINAL_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_spurgeon_original_cache(cache):
    os.makedirs(os.path.dirname(SPURGEON_ORIGINAL_CACHE_FILE), exist_ok=True)
    with open(SPURGEON_ORIGINAL_CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# ── Custom TextView with theme-coloured cursor ────────────────────────────────
# GTK4/libadwaita ignores CSS cursor-colour overrides when the system colour
# scheme differs from the app's forced scheme. This subclass hides the native
# cursor and paints a correctly-coloured one in do_snapshot() instead.

class StyledTextView(Gtk.TextView):
    __gtype_name__ = "StyledTextView"
    _BLINK_MS = 530

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._cursor_rgba = None
        self._blink_on = True
        self._blink_id = None
        self.connect("notify::has-focus", self._on_focus_change)
        self.get_buffer().connect(
            "notify::cursor-position", lambda *_: self.queue_draw()
        )

    def set_cursor_rgba(self, rgba):
        self._cursor_rgba = rgba
        self.set_cursor_visible(False)
        self.queue_draw()

    def _on_focus_change(self, *_):
        if self.has_focus():
            self._blink_on = True
            if self._blink_id is None:
                self._blink_id = GLib.timeout_add(self._BLINK_MS, self._blink_tick)
        else:
            if self._blink_id is not None:
                GLib.source_remove(self._blink_id)
                self._blink_id = None
            self._blink_on = False
        self.queue_draw()

    def _blink_tick(self):
        self._blink_on = not self._blink_on
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def do_snapshot(self, snapshot):
        Gtk.TextView.do_snapshot(self, snapshot)
        if not self._cursor_rgba or not self.has_focus() or not self._blink_on:
            return
        buf = self.get_buffer()
        it = buf.get_iter_at_mark(buf.get_insert())
        rect = self.get_iter_location(it)
        wx, wy = self.buffer_to_window_coords(
            Gtk.TextWindowType.WIDGET, rect.x, rect.y
        )
        r = Graphene.Rect()
        r.init(wx, wy, 2.0, max(float(rect.height), 1.0))
        snapshot.append_color(self._cursor_rgba, r)


# ── Main Window ───────────────────────────────────────────────────────────────

class MorningDashboard(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="☀️  Morning Dashboard")
        self.set_resizable(True)
        self.set_size_request(600, 400)

        settings = Gtk.Settings.get_default()
        settings.props.gtk_cursor_blink = True
        settings.props.gtk_cursor_blink_timeout = 0  # never stop blinking

        self.prefs = load_prefs()
        self.font_size = self.prefs.get("font_size", 13)
        self.theme = self.prefs.get("theme", "dark")
        self.weather_location = self.prefs.get("weather_location", "")
        self.weather_lat      = self.prefs.get("weather_lat", None)
        self.weather_lon      = self.prefs.get("weather_lon", None)
        self.enabled_calendars = self.prefs.get("enabled_calendars", [])
        self.visible_tabs = self.prefs.get("visible_tabs", ALL_TABS[:])
        self.tab_order = self.prefs.get("tab_order", ALL_TABS[:])
        # Newly-introduced tabs are inserted at their canonical position from
        # ALL_TABS (not just appended at the end) and made visible by default,
        # so a brand-new tab shows up in the right place for existing users
        # without them having to visit Settings first.
        for idx, key in enumerate(ALL_TABS):
            if key not in self.tab_order:
                self.tab_order.insert(min(idx, len(self.tab_order)), key)
                if key not in self.visible_tabs:
                    self.visible_tabs.append(key)
        self.api_bible_key = self.prefs.get("api_bible_key", "")
        self.claude_api_key = self.prefs.get("claude_api_key", "")
        self.spurgeon_paned_position = self.prefs.get("spurgeon_paned_position", 700)
        self.web_url  = self.prefs.get("web_url", "")
        self.web_user = self.prefs.get("web_user", "")
        self.web_pass = self.prefs.get("web_pass", "")

        # Restore window size
        win_w = self.prefs.get("window_width", 900)
        win_h = self.prefs.get("window_height", 650)
        self.set_default_size(win_w, win_h)

        self.connect("close-request", self._on_close_request)

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

        # Main body: sidebar + content stack
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_vexpand(True)
        root.append(body)

        # Sidebar: fixed icon column + collapsible label revealer
        self._sidebar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._sidebar.add_css_class("sidebar")
        self._sidebar.set_vexpand(True)
        body.append(self._sidebar)

        # Icon column (always visible, fixed width)
        self._icon_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._icon_col.add_css_class("sidebar-icon-col")
        self._icon_col.set_vexpand(True)
        self._sidebar.append(self._icon_col)

        # Label column inside a Revealer (slides in/out)
        self._label_revealer = Gtk.Revealer()
        self._label_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_RIGHT)
        self._label_revealer.set_transition_duration(200)
        self._label_revealer.set_reveal_child(True)
        self._label_revealer.set_hexpand(False)

        self._label_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._label_col.add_css_class("sidebar-label-col")
        self._label_col.set_vexpand(True)
        self._label_revealer.set_child(self._label_col)
        self._sidebar.append(self._label_revealer)

        # Content stack
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        body.append(self.stack)

        # Tab definitions: key -> (emoji, label, accent colour)
        self._tab_meta = {
            "spurgeon": ("📖", "Devotional", "#f0a500"),
            "news":     ("📰", "News",       "#4a9eff"),
            "weather":  ("🌤️", "Weather",    "#00bcd4"),
            "sermons":  ("✍️", "Sermons",    "#66bb6a"),
            "calendar": ("📅", "Calendar",   "#ab47bc"),
            "bible":    ("📜", "Bible",      "#ffd54f"),
            "prayer":   ("🙏", "Prayer",     "#ef5350"),
            "notes":    ("📝", "Notes",      "#ff7043"),
            "systematics": ("📚", "Theology", "#7e57c2"),
        }
        self._sidebar_buttons = {}    # key -> (icon_row, icon_btn, label_btn)
        self._sidebar_indicators = {} # key -> indicator Box

        self._build_spurgeon_tab()
        self._build_news_tab()
        self._build_weather_tab()
        self._build_sermon_tab()
        self._build_calendar_tab()
        self._build_bible_tab()
        self._build_prayer_tab()
        self._build_notes_tab()
        self._build_systematics_tab()

        # Store page widgets by key
        self._tab_widgets = {key: self.stack.get_child_by_name(key) for key in self._tab_meta}

        self._build_sidebar_buttons()
        self._apply_tab_order()
        self._apply_tab_visibility()

        # Show first visible tab
        for key in self.tab_order:
            if key in self.visible_tabs:
                self._switch_tab(key)
                break

    # ── Tab ordering and visibility ───────────────────────────────────────────

    def _build_sidebar_buttons(self):
        """Create sidebar buttons split across icon column and label column."""
        for key, (emoji, label, accent) in self._tab_meta.items():
            # Icon button (in fixed icon column)
            icon_btn = Gtk.Button(label=emoji)
            icon_btn.add_css_class("sidebar-icon-btn")
            icon_btn.set_tooltip_text(label)
            icon_btn.connect("clicked", lambda b, k=key: self._switch_tab(k))

            # Indicator bar sits to the left of the icon button
            indicator = Gtk.Box()
            indicator.set_size_request(3, -1)
            indicator.add_css_class("sidebar-indicator")
            indicator.add_css_class(f"sidebar-indicator-{key}")
            indicator.set_visible(False)

            icon_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            icon_row.append(indicator)
            icon_row.append(icon_btn)
            self._icon_col.append(icon_row)

            # Label button (in collapsible label column)
            label_btn = Gtk.Button(label=label)
            label_btn.add_css_class("sidebar-label-btn")
            label_btn.set_halign(Gtk.Align.FILL)
            label_btn.set_hexpand(True)
            label_btn.connect("clicked", lambda b, k=key: self._switch_tab(k))
            self._label_col.append(label_btn)

            self._sidebar_buttons[key] = (icon_row, icon_btn, label_btn)
            self._sidebar_indicators[key] = indicator

        # Spacer + collapse button in icon column
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        self._icon_col.append(spacer)

        self._sidebar_collapsed = self.prefs.get("sidebar_collapsed", False)
        self._collapse_btn = Gtk.Button(label="▶" if self._sidebar_collapsed else "◀")
        self._collapse_btn.add_css_class("sidebar-collapse-btn")
        self._collapse_btn.set_tooltip_text("Expand sidebar" if self._sidebar_collapsed else "Collapse sidebar")
        self._collapse_btn.connect("clicked", self._toggle_sidebar)
        self._icon_col.append(self._collapse_btn)
        self._label_revealer.set_reveal_child(not self._sidebar_collapsed)

        # Matching spacer in label column so heights align
        label_spacer = Gtk.Box()
        label_spacer.set_vexpand(True)
        self._label_col.append(label_spacer)

    def _toggle_sidebar(self, btn):
        """Collapse/expand the label column via Revealer."""
        self._sidebar_collapsed = not self._sidebar_collapsed
        self._label_revealer.set_reveal_child(not self._sidebar_collapsed)
        if self._sidebar_collapsed:
            self._collapse_btn.set_label("▶")
            self._collapse_btn.set_tooltip_text("Expand sidebar")
        else:
            self._collapse_btn.set_label("◀")
            self._collapse_btn.set_tooltip_text("Collapse sidebar")
        self.prefs["sidebar_collapsed"] = self._sidebar_collapsed
        save_prefs(self.prefs)

    def _switch_tab(self, key):
        """Switch stack to key and update sidebar active state."""
        self.stack.set_visible_child_name(key)
        self._active_tab = key

        for k, (icon_row, icon_btn, label_btn) in self._sidebar_buttons.items():
            indicator = self._sidebar_indicators.get(k)
            active = (k == key)
            if active:
                icon_btn.add_css_class("sidebar-icon-btn-active")
                label_btn.add_css_class("sidebar-label-btn-active")
                if indicator:
                    indicator.set_visible(True)
            else:
                icon_btn.remove_css_class("sidebar-icon-btn-active")
                label_btn.remove_css_class("sidebar-label-btn-active")
                if indicator:
                    indicator.set_visible(False)

    def _apply_tab_order(self):
        """Rebuild sidebar buttons in current tab_order."""
        order = self.tab_order if self.tab_order else ALL_TABS[:]
        visible = set(self.visible_tabs) if self.visible_tabs else set(ALL_TABS)
        # Remove all tab rows from both columns
        for key, (icon_row, icon_btn, label_btn) in self._sidebar_buttons.items():
            if icon_row.get_parent() == self._icon_col:
                self._icon_col.remove(icon_row)
            if label_btn.get_parent() == self._label_col:
                self._label_col.remove(label_btn)
        # Re-insert in order at top of each column
        for key in reversed(order):
            if key not in visible:
                continue
            icon_row, icon_btn, label_btn = self._sidebar_buttons[key]
            self._icon_col.prepend(icon_row)
            self._label_col.prepend(label_btn)

    def _apply_tab_visibility(self):
        """Show/hide stack pages and rebuild sidebar to match."""
        visible = self.visible_tabs if self.visible_tabs else ALL_TABS[:]
        for key, widget in self._tab_widgets.items():
            if widget:
                widget.set_visible(key in visible)
        # Rebuild sidebar (handles both order and visibility)
        self._apply_tab_order()
        # If current visible child is now hidden, switch to first visible
        current = self.stack.get_visible_child_name()
        if current not in visible:
            for key in (self.tab_order or ALL_TABS):
                if key in visible:
                    self._switch_tab(key)
                    break

    def _on_close_request(self, *args):
        if hasattr(self, "_notes_save_id") and self._notes_save_id is not None:
            GLib.source_remove(self._notes_save_id)
            self._notes_save()
        if hasattr(self, "_spurgeon_notes_save_id") and self._spurgeon_notes_save_id is not None:
            GLib.source_remove(self._spurgeon_notes_save_id)
            self._spurgeon_notes_save()

        w, h = self.get_width(), self.get_height()
        if w > 0 and h > 0:
            self.prefs["window_width"] = w
            self.prefs["window_height"] = h
        save_prefs(self.prefs)
        return False

    # ── CSS ───────────────────────────────────────────────────────────────────

    def _apply_css(self):
        fs = self.font_size
        dark = self.theme == "dark"

        Gtk.Settings.get_default().props.gtk_application_prefer_dark_theme = dark
        try:
            gi.require_version('Adw', '1')
            from gi.repository import Adw
            mgr = Adw.StyleManager.get_default()
            if dark:
                mgr.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            else:
                mgr.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        except Exception:
            pass

        # Remove old provider and add fresh one to force full restyle
        try:
            Gtk.StyleContext.remove_provider_for_display(
                self.get_display(), self.css_provider
            )
        except Exception:
            pass
        self.css_provider = Gtk.CssProvider()

        # Colours
        bg          = "#1a1a2e" if dark else "#f4f4f8"
        header_bg   = "#16213e" if dark else "#e8eaf2"
        header_border = "#0f3460" if dark else "#c8cde0"
        text        = "#e0e0e0" if dark else "#1a1a2e"
        subtext     = "#a0a0c0" if dark else "#555570"
        reading     = "#d0d0e8" if dark else "#2a2a3e"
        tab_bg      = "#16213e" if dark else "#e8eaf2"
        tab_active  = "#0f3460" if dark else "#ffffff"
        accent      = "#e94560" if dark else "#c0392b"
        btn_bg      = "#0f3460" if dark else "#dde2f0"
        news_text   = "#c0c0e0" if dark else "#333355"
        weather_bg  = "#16213e" if dark else "#eef0f8"
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
            .sidebar {{
                background-color: {header_bg};
                border-right: 1px solid {header_border};
            }}
            .sidebar-icon-col {{
                background-color: {header_bg};
                padding: 8px 0;
                min-width: 44px;
            }}
            .sidebar-label-col {{
                background-color: {header_bg};
                padding: 8px 4px 8px 0;
                min-width: 130px;

            }}
            .sidebar-icon-btn {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
                padding: 8px;
                font-size: 18px;
                color: {subtext};
                min-width: 36px;
                margin: 2px 4px;
                transition: background-color 150ms ease;
            }}
            .sidebar-icon-btn:hover {{
                background-color: {tab_active};
            }}
            .sidebar-icon-btn-active {{
                background-color: {tab_active};
                color: {text};
            }}
            .sidebar-label-btn {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: {fs - 1}px;
                font-weight: bold;
                color: {subtext};
                margin: 2px 0;
                transition: background-color 150ms ease;
            }}
            .sidebar-label-btn:hover {{
                background-color: {tab_active};
                color: {text};
            }}
            .sidebar-label-btn-active {{
                background-color: {tab_active};
                color: {text};
            }}
            .sidebar-collapse-btn {{
                background-color: transparent;
                color: {subtext};
                border: none;
                border-radius: 8px;
                margin: 4px;
                padding: 6px 8px;
                font-size: 11px;
            }}
            .sidebar-collapse-btn:hover {{
                background-color: {tab_active};
                color: {text};
            }}
            .sidebar-emoji {{ font-size: 18px; }}
            .sidebar-label {{ font-size: {fs - 1}px; font-weight: bold; }}
            .sidebar-indicator {{ border-radius: 2px; }}
            .sidebar-indicator-spurgeon {{ background-color: #f0a500; }}
            .sidebar-indicator-news     {{ background-color: #4a9eff; }}
            .sidebar-indicator-weather  {{ background-color: #00bcd4; }}
            .sidebar-indicator-sermons  {{ background-color: #66bb6a; }}
            .sidebar-indicator-calendar {{ background-color: #ab47bc; }}
            .sidebar-indicator-bible    {{ background-color: #ffd54f; }}
            .sidebar-indicator-prayer   {{ background-color: #ef5350; }}
            .sidebar-indicator-notes    {{ background-color: #ff7043; }}
            .sidebar-indicator-systematics {{ background-color: #7e57c2; }}
            .tab-content {{ background-color: {bg}; padding: 20px; }}
            .card {{
                background-color: {tab_active};
                border-radius: 12px;
                padding: 16px 20px;
                margin-bottom: 8px;
            }}
            .card-subtle {{
                background-color: {header_bg};
                border-radius: 10px;
                padding: 12px 16px;
                margin-bottom: 6px;
            }}
            .spur-comment-card {{
                background-color: {'transparent' if dark else '#ffffff'};
                border-left: 3px solid {'#f0a500' if dark else '#b87800'};
                border-radius: 0 4px 4px 0;
                padding: 6px 10px;
                margin-bottom: 4px;
            }}
            .spur-comment-ts {{
                color: {subtext};
            }}
            .spur-comment-text {{
                color: {text};
            }}
            .section-title {{
                font-size: 16px; font-weight: bold;
                color: {accent}; margin-bottom: 10px;
            }}
            .reading-text {{
                font-size: {fs}px;
                color: {reading};
                line-height: 1.8;
            }}
            .reading-text, .reading-text text, .reading-text text cursor {{
                font-size: {fs}px;
                color: {reading} !important;
                background-color: {bg} !important;
                caret-color: {reading} !important;
                -gtk-cursor-color: {reading} !important;
            }}
            .reading-text text cursor {{
                color: {reading} !important;
                background-color: {reading} !important;
                border-color: {reading} !important;
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
            .weather-icon {{ font-size: 72px; }}
            .weather-temp {{ font-size: 48px; font-weight: bold; color: {text}; }}
            .weather-desc {{ font-size: 14px; color: {subtext}; }}
            .forecast-card {{
                background-color: {weather_bg};
                border-radius: 12px;
                padding: 12px 8px;
            }}
            .forecast-day  {{ font-size: {fs - 1}px; color: {subtext}; font-weight: bold; }}
            .forecast-icon {{ font-size: 28px; }}
            .forecast-hi   {{ font-size: {fs}px; color: #e94560; font-weight: bold; }}
            .forecast-lo   {{ font-size: {fs - 1}px; color: {subtext}; }}
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
                color: {text};
                font-size: 12px;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                margin-left: 4px;
            }}
            .sermon-btn:hover {{ background-color: {accent}; color: #ffffff; }}
            .cancel-btn {{
                background-color: {accent};
                color: #ffffff;
                font-size: 12px;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                margin-left: 4px;
            }}
            .cancel-btn:hover {{ background-color: #ff2244; color: #ffffff; }}
            .sermon-list-item {{
                background-color: {tab_active};
                border-radius: 6px;
                padding: 6px 10px;
                margin-bottom: 2px;
                color: {text};
                font-size: {fs}px;
            }}
            .sermon-list-item:hover {{ background-color: {accent}; color: #ffffff; }}
            /* Universal Caret/Cursor Styling for All Input Widgets */
            entry, entry text, textview, textview text, text, cursor, .cursor {{
                caret-color: {text} !important;
                -gtk-cursor-color: {text} !important;
            }}
            entry text cursor, textview text cursor, cursor, .cursor {{
                color: {text} !important;
                background-color: {text} !important;
                border-color: {text} !important;
            }}
            textview, textview text {{
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
            .bible-verse, .bible-verse text, .bible-verse text cursor {{
                color: {reading} !important;
                background-color: {bg} !important;
                caret-color: {reading} !important;
                -gtk-cursor-color: {reading} !important;
            }}
            .bible-verse text cursor {{
                color: {reading} !important;
                background-color: {reading} !important;
                border-color: {reading} !important;
            }}
            .spurgeon-notes {{
                background-color: #2d1b0e !important;
                color: #d4a96a !important;
            }}
            .spurgeon-notes, .spurgeon-notes text, .spurgeon-notes text cursor {{
                background-color: #2d1b0e !important;
                color: #d4a96a !important;
                caret-color: #d4a96a !important;
                -gtk-cursor-color: #d4a96a !important;
            }}
            .spurgeon-notes text cursor {{
                color: #d4a96a !important;
                background-color: #d4a96a !important;
                border-color: #d4a96a !important;
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
            .prayer-diary-banner {{
                background-color: {'#3a1a1a' if dark else '#fff5f5'};
                border-left: 3px solid #ef5350;
                border-radius: 0 6px 6px 0;
                padding: 8px 14px;
            }}
            .prayer-diary-day {{
                font-size: {fs}px;
                font-weight: bold;
                color: #ef5350;
            }}
            .prayer-diary-names {{
                font-size: {fs}px;
                color: {text};
            }}
            .prayer-diary-theme {{
                font-size: {max(fs - 1, 10)}px;
                color: {subtext};
                font-style: italic;
            }}
            .prefs-box {{
                background-color: {bg};
                color: {text};
            }}
            .prefs-box label {{
                color: {text};
            }}
            .prefs-box checkbutton label {{
                color: {text};
            }}
            .prefs-box spinbutton {{
                background-color: {tab_active};
                color: {text};
            }}
            .prefs-box spinbutton entry {{
                background-color: {tab_active};
                color: {text};
            }}
            .prefs-box spinbutton entry text {{
                background-color: {tab_active};
                color: {text};
            }}
            .prefs-box dropdown {{
                background-color: {btn_bg};
                color: {text};
            }}
            .prefs-box dropdown button {{
                background-color: {btn_bg};
                color: {text};
            }}
            .prefs-box dropdown button label {{
                color: {text};
            }}
            popover {{
                background-color: {tab_active};
                color: {text};
            }}
            popover contents {{
                background-color: {tab_active};
                color: {text};
            }}
            popover listview {{
                background-color: {tab_active};
                color: {text};
            }}
            popover listview row {{
                background-color: {tab_active};
                color: {text};
            }}
            popover listview row label {{
                color: {text};
            }}
            popover listview row:hover {{
                background-color: {btn_bg};
            }}
            .bible-verse-num {{
                font-size: {fs - 2}px;
                color: {accent};
                font-weight: bold;
            }}
            .bible-citation {{
                font-size: {fs - 3}px;
                color: {subtext};
                font-style: italic;
            }}
        """.encode()
        self.css_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_USER
        )

        cursor_rgba = Gdk.RGBA()
        cursor_rgba.parse(text)
        self._theme_cursor_rgba = cursor_rgba
        for attr in ("sermon_view", "notes_view"):
            view = getattr(self, attr, None)
            if view is not None:
                view.set_cursor_rgba(cursor_rgba)

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
        box.add_css_class("prefs-box")
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
        font_val = {"v": self.font_size}
        font_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        font_lbl = Gtk.Label(label="Reading font size:")
        font_lbl.set_hexpand(True)
        font_lbl.set_halign(Gtk.Align.START)
        dec_btn = Gtk.Button(label="−")
        dec_btn.add_css_class("sermon-btn")
        font_size_lbl = Gtk.Label(label=str(self.font_size))
        font_size_lbl.set_width_chars(3)
        font_size_lbl.set_halign(Gtk.Align.CENTER)
        inc_btn = Gtk.Button(label="+")
        inc_btn.add_css_class("sermon-btn")
        def on_dec(b):
            if font_val["v"] > 9:
                font_val["v"] -= 1
                font_size_lbl.set_text(str(font_val["v"]))
        def on_inc(b):
            if font_val["v"] < 24:
                font_val["v"] += 1
                font_size_lbl.set_text(str(font_val["v"]))
        dec_btn.connect("clicked", on_dec)
        inc_btn.connect("clicked", on_inc)
        font_row.append(font_lbl)
        font_row.append(dec_btn)
        font_row.append(font_size_lbl)
        font_row.append(inc_btn)
        box.append(font_row)

        # Theme row
        theme_val = {"v": self.theme}
        theme_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        theme_lbl = Gtk.Label(label="Theme:")
        theme_lbl.set_hexpand(True)
        theme_lbl.set_halign(Gtk.Align.START)
        dark_radio = Gtk.CheckButton(label="Dark")
        dark_radio.set_active(self.theme == "dark")
        light_radio = Gtk.CheckButton(label="Light")
        light_radio.set_active(self.theme == "light")
        light_radio.set_group(dark_radio)
        def on_dark_toggled(b):
            if b.get_active():
                theme_val["v"] = "dark"
        def on_light_toggled(b):
            if b.get_active():
                theme_val["v"] = "light"
        dark_radio.connect("toggled", on_dark_toggled)
        light_radio.connect("toggled", on_light_toggled)
        theme_row.append(theme_lbl)
        theme_row.append(dark_radio)
        theme_row.append(light_radio)
        box.append(theme_row)

        # Start with OS row
        startup_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        startup_lbl = Gtk.Label(label="Start with OS:")
        startup_lbl.set_hexpand(True)
        startup_lbl.set_halign(Gtk.Align.START)
        startup_check = Gtk.CheckButton(label="Launch at login")
        startup_check.set_active(os.path.exists(AUTOSTART_FILE))
        startup_row.append(startup_lbl)
        startup_row.append(startup_check)
        box.append(startup_row)

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
        loc_entry.add_css_class("sermon-title-entry")
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
        selected_location = {"name": self.weather_location, "lat": self.weather_lat, "lon": self.weather_lon}

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

        # ── API.Bible key ─────────────────────────────────────────────────────
        bible_api_header = Gtk.Label(label="BIBLE (API.BIBLE)")
        bible_api_header.add_css_class("source-label")
        bible_api_header.set_halign(Gtk.Align.START)
        box.append(bible_api_header)

        bible_key_row0 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bible_key_pre = Gtk.Label(label="Free API key from")
        bible_key_pre.add_css_class("date-label")
        bible_key_link = Gtk.LinkButton.new_with_label("https://api.bible", "api.bible")
        bible_key_link.add_css_class("date-label")
        bible_key_post = Gtk.Label(label="— required for CSB, NLT and NIV.")
        bible_key_post.add_css_class("date-label")
        bible_key_row0.set_halign(Gtk.Align.START)
        bible_key_row0.append(bible_key_pre)
        bible_key_row0.append(bible_key_link)
        bible_key_row0.append(bible_key_post)
        box.append(bible_key_row0)

        bible_key_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bible_key_lbl = Gtk.Label(label="API key:")
        bible_key_lbl.set_halign(Gtk.Align.START)
        bible_key_entry = Gtk.Entry()
        bible_key_entry.set_text(self.api_bible_key)
        bible_key_entry.set_placeholder_text("Paste your API.Bible key here…")
        bible_key_entry.set_hexpand(True)
        bible_key_entry.set_visibility(False)
        bible_key_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        show_key_btn = Gtk.CheckButton(label="Show")
        show_key_btn.connect("toggled", lambda b: bible_key_entry.set_visibility(b.get_active()))
        bible_key_row.append(bible_key_lbl)
        bible_key_row.append(bible_key_entry)
        bible_key_row.append(show_key_btn)
        box.append(bible_key_row)

        # ── Claude API key (Spurgeon modernisation) ────────────────────────────
        claude_header = Gtk.Label(label="DEVOTIONAL — MODERN ENGLISH (CLAUDE API)")
        claude_header.add_css_class("source-label")
        claude_header.set_halign(Gtk.Align.START)
        box.append(claude_header)

        claude_row0 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        claude_pre = Gtk.Label(label="API key from")
        claude_pre.add_css_class("date-label")
        claude_link = Gtk.LinkButton.new_with_label("https://console.anthropic.com", "console.anthropic.com")
        claude_link.add_css_class("date-label")
        claude_post = Gtk.Label(label="— used for the ✨ Modernise button on the Devotional tab.")
        claude_post.add_css_class("date-label")
        claude_row0.set_halign(Gtk.Align.START)
        claude_row0.append(claude_pre)
        claude_row0.append(claude_link)
        claude_row0.append(claude_post)
        box.append(claude_row0)

        claude_key_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        claude_key_lbl = Gtk.Label(label="API key:")
        claude_key_lbl.set_halign(Gtk.Align.START)
        claude_key_entry = Gtk.Entry()
        claude_key_entry.set_text(self.claude_api_key)
        claude_key_entry.set_placeholder_text("Paste your Claude API key here…")
        claude_key_entry.set_hexpand(True)
        claude_key_entry.set_visibility(False)
        claude_key_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        show_claude_key_btn = Gtk.CheckButton(label="Show")
        show_claude_key_btn.connect("toggled", lambda b: claude_key_entry.set_visibility(b.get_active()))
        claude_key_row.append(claude_key_lbl)
        claude_key_row.append(claude_key_entry)
        claude_key_row.append(show_claude_key_btn)
        box.append(claude_key_row)

        # ── Tabs to show / order ──────────────────────────────────────────────
        tabs_header = Gtk.Label(label="TABS — ORDER & VISIBILITY")
        tabs_header.add_css_class("source-label")
        tabs_header.set_halign(Gtk.Align.START)
        box.append(tabs_header)

        TAB_LABELS = {
            "spurgeon": "📖 Devotional",
            "news":     "📰 News",
            "weather":  "🌤️ Weather",
            "sermons":  "✍️ Sermons",
            "calendar": "📅 Calendar",
            "bible":    "📜 Bible",
            "prayer":   "🙏 Prayer",
            "notes":    "📝 Notes",
            "systematics": "📚 Theology",
        }

        # Ensure tab_order contains all keys (handle new tabs added after pref was saved)
        saved_order = self.tab_order[:]
        for k in ALL_TABS:
            if k not in saved_order:
                saved_order.append(k)
        tab_order_state = saved_order
        tab_visible_state = set(self.visible_tabs)

        tab_checks = {}  # key -> CheckButton (for save logic)
        rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.append(rows_box)

        def rebuild_tab_rows():
            child = rows_box.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                rows_box.remove(child)
                child = nxt
            tab_checks.clear()
            n = len(tab_order_state)
            for i, key in enumerate(tab_order_state):
                label = TAB_LABELS.get(key, key)
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

                up_btn = Gtk.Button(label="↑")
                up_btn.add_css_class("sermon-btn")
                up_btn.set_sensitive(i > 0)
                up_btn.set_size_request(28, -1)
                def on_up(b, k=key):
                    idx = tab_order_state.index(k)
                    if idx > 0:
                        tab_order_state[idx], tab_order_state[idx - 1] = tab_order_state[idx - 1], tab_order_state[idx]
                        rebuild_tab_rows()
                up_btn.connect("clicked", on_up)

                down_btn = Gtk.Button(label="↓")
                down_btn.add_css_class("sermon-btn")
                down_btn.set_sensitive(i < n - 1)
                down_btn.set_size_request(28, -1)
                def on_down(b, k=key):
                    idx = tab_order_state.index(k)
                    if idx < len(tab_order_state) - 1:
                        tab_order_state[idx], tab_order_state[idx + 1] = tab_order_state[idx + 1], tab_order_state[idx]
                        rebuild_tab_rows()
                down_btn.connect("clicked", on_down)

                check = Gtk.CheckButton(label=label)
                check.set_active(key in tab_visible_state)
                def on_toggle(cb, k=key):
                    if cb.get_active():
                        tab_visible_state.add(k)
                    else:
                        tab_visible_state.discard(k)
                check.connect("toggled", on_toggle)
                tab_checks[key] = check

                row.append(up_btn)
                row.append(down_btn)
                row.append(check)
                rows_box.append(row)

        rebuild_tab_rows()

        tabs_note = Gtk.Label(label="(At least one tab must remain visible)")
        tabs_note.add_css_class("date-label")
        tabs_note.set_halign(Gtk.Align.START)
        box.append(tabs_note)

        # ── Calendar selection ────────────────────────────────────────────────
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
            last = cal_header
            for cal_id, cal_name in cals:
                check = Gtk.CheckButton(label=cal_name)
                active = (not self.enabled_calendars or
                          cal_id in self.enabled_calendars)
                check.set_active(active)
                cal_checks[cal_id] = check
                box.insert_child_after(check, last)
                last = check

        threading.Thread(target=load_cals, daemon=True).start()

        _state = {"saved": False, "cancelled": False}

        def do_save():
            if _state["saved"] or _state["cancelled"]:
                return
            _state["saved"] = True
            self._save_prefs(
                font_val["v"],
                theme_val["v"],
                selected_location["name"],
                selected_location.get("lat"),
                selected_location.get("lon"),
                [cal_id for cal_id, check in cal_checks.items() if check.get_active()],
                list(tab_visible_state) or ALL_TABS[:],
                tab_order_state[:],
                bible_key_entry.get_text().strip(),
                web_url_entry.get_text().strip(),
                web_user_entry.get_text().strip(),
                web_pass_entry.get_text(),
                claude_key_entry.get_text().strip(),
            )
            if startup_check.get_active():
                os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
                script = os.path.abspath(__file__)
                with open(AUTOSTART_FILE, "w") as f:
                    f.write(f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Morning Dashboard
Comment=Your daily briefing — devotional, news and weather
Exec=python3 {script}
Icon={os.path.join(os.path.dirname(script), 'icon.png')}
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
""")
            else:
                if os.path.exists(AUTOSTART_FILE):
                    os.remove(AUTOSTART_FILE)

        def on_close_request(d):
            do_save()
            return False

        dialog.connect("close-request", on_close_request)

        # ── Web App Sync ──────────────────────────────────────────────────────
        web_header = Gtk.Label(label="WEB APP SYNC")
        web_header.add_css_class("source-label")
        web_header.set_halign(Gtk.Align.START)
        box.append(web_header)

        def _web_row(label_text, default, visibility=True):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lbl = Gtk.Label(label=label_text)
            lbl.add_css_class("date-label")
            lbl.set_width_chars(10)
            lbl.set_halign(Gtk.Align.START)
            entry = Gtk.Entry()
            entry.set_text(default)
            entry.set_hexpand(True)
            entry.set_visibility(visibility)
            row.append(lbl)
            row.append(entry)
            box.append(row)
            return entry

        web_url_entry  = _web_row("URL:",      self.web_url)
        web_user_entry = _web_row("Username:", self.web_user)
        web_pass_entry = _web_row("Password:", self.web_pass, visibility=False)

        web_sync_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        push_btn = Gtk.Button(label="⬆ Push prayers to web")
        push_btn.add_css_class("sermon-btn")
        pull_btn = Gtk.Button(label="⬇ Pull prayers from web")
        pull_btn.add_css_class("sermon-btn")
        web_sync_row.append(push_btn)
        web_sync_row.append(pull_btn)
        box.append(web_sync_row)

        self._web_sync_status = Gtk.Label(label="")
        self._web_sync_status.add_css_class("date-label")
        self._web_sync_status.set_halign(Gtk.Align.START)
        self._web_sync_status.set_wrap(True)
        box.append(self._web_sync_status)

        def on_push(b):
            self._prayer_push_to_web(
                web_url_entry.get_text().strip(),
                web_user_entry.get_text().strip(),
                web_pass_entry.get_text(),
                self._web_sync_status,
            )
        def on_pull(b):
            self._prayer_pull_from_web(
                web_url_entry.get_text().strip(),
                web_user_entry.get_text().strip(),
                web_pass_entry.get_text(),
                self._web_sync_status,
            )
        push_btn.connect("clicked", on_push)
        pull_btn.connect("clicked", on_pull)

        spurgeon_notes_sync_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spurgeon_notes_push_btn = Gtk.Button(label="⬆ Push Spurgeon notes to web")
        spurgeon_notes_push_btn.add_css_class("sermon-btn")
        spurgeon_notes_pull_btn = Gtk.Button(label="⬇ Pull Spurgeon notes from web")
        spurgeon_notes_pull_btn.add_css_class("sermon-btn")
        spurgeon_notes_sync_row.append(spurgeon_notes_push_btn)
        spurgeon_notes_sync_row.append(spurgeon_notes_pull_btn)
        box.append(spurgeon_notes_sync_row)

        def on_spurgeon_notes_push(b):
            self._spurgeon_notes_push_to_web(
                web_url_entry.get_text().strip(),
                web_user_entry.get_text().strip(),
                web_pass_entry.get_text(),
                self._web_sync_status,
            )
        def on_spurgeon_notes_pull(b):
            self._spurgeon_notes_pull_from_web(
                web_url_entry.get_text().strip(),
                web_user_entry.get_text().strip(),
                web_pass_entry.get_text(),
                self._web_sync_status,
            )
        spurgeon_notes_push_btn.connect("clicked", on_spurgeon_notes_push)
        spurgeon_notes_pull_btn.connect("clicked", on_spurgeon_notes_pull)

        # ── Web App Admin ──────────────────────────────────────────────────────
        admin_header = Gtk.Label(label="WEB APP ADMIN")
        admin_header.add_css_class("source-label")
        admin_header.set_halign(Gtk.Align.START)
        box.append(admin_header)

        admin_requests_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        admin_status_lbl = Gtk.Label(label="")
        admin_status_lbl.add_css_class("date-label")
        admin_status_lbl.set_halign(Gtk.Align.START)
        admin_status_lbl.set_wrap(True)

        load_req_btn = Gtk.Button(label="🔄 Load access requests")
        load_req_btn.add_css_class("sermon-btn")
        load_req_btn.connect("clicked", lambda b: self._admin_load_requests(
            web_url_entry.get_text().strip(),
            web_user_entry.get_text().strip(),
            web_pass_entry.get_text(),
            admin_requests_box,
            admin_status_lbl,
        ))
        box.append(load_req_btn)
        box.append(admin_status_lbl)
        box.append(admin_requests_box)

        # ── Export / Import ───────────────────────────────────────────────────
        data_header = Gtk.Label(label="PERSONAL DATA")
        data_header.add_css_class("source-label")
        data_header.set_halign(Gtk.Align.START)
        box.append(data_header)

        self._backup_status = Gtk.Label(label="")
        self._backup_status.add_css_class("date-label")
        self._backup_status.set_halign(Gtk.Align.START)
        self._backup_status.set_wrap(True)

        data_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        export_btn = Gtk.Button(label="⬆ Export backup")
        export_btn.add_css_class("sermon-btn")
        export_btn.connect("clicked", self._export_data)
        import_btn = Gtk.Button(label="⬇ Import backup")
        import_btn.add_css_class("sermon-btn")
        import_btn.connect("clicked", self._import_data)
        drive_btn = Gtk.Button(label="☁ Backup to Drive")
        drive_btn.add_css_class("sermon-btn")
        drive_btn.connect("clicked", self._backup_to_drive)
        data_row.append(export_btn)
        data_row.append(import_btn)
        data_row.append(drive_btn)
        box.append(data_row)
        box.append(self._backup_status)

        # Buttons
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("cancel-btn")
        def on_cancel(b):
            _state["cancelled"] = True
            dialog.close()
        cancel_btn.connect("clicked", on_cancel)
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        def on_save(b):
            do_save()
            dialog.close()
        save_btn.connect("clicked", on_save)
        btn_row.append(cancel_btn)
        btn_row.append(save_btn)
        box.append(btn_row)

        outer.set_child(box)
        dialog.set_child(outer)
        dialog.present()

    def _save_prefs(self, font_size, theme, weather_location, weather_lat, weather_lon, enabled_calendars, visible_tabs, tab_order, api_bible_key="", web_url="", web_user="", web_pass="", claude_api_key=""):
        self.font_size = font_size
        self.theme = theme
        self.weather_location = weather_location
        self.weather_lat = weather_lat
        self.weather_lon = weather_lon
        self.enabled_calendars = enabled_calendars
        self.visible_tabs = visible_tabs
        self.tab_order = tab_order
        self.api_bible_key = api_bible_key
        self.web_url  = web_url
        self.web_user = web_user
        self.web_pass = web_pass
        self.claude_api_key = claude_api_key
        self.prefs.update({
            "font_size": font_size,
            "theme": theme,
            "weather_location": weather_location,
            "weather_lat": weather_lat,
            "weather_lon": weather_lon,
            "enabled_calendars": enabled_calendars,
            "visible_tabs": visible_tabs,
            "tab_order": tab_order,
            "api_bible_key": api_bible_key,
            "web_url":  web_url,
            "web_user": web_user,
            "web_pass": web_pass,
            "claude_api_key": claude_api_key,
        })
        save_prefs(self.prefs)
        self._apply_css()
        self._apply_tab_order()
        self._apply_tab_visibility()
        # Force GTK to re-render all widgets with new styles
        self.queue_draw()
        child = self.get_child()
        if child:
            child.queue_draw()
        threading.Thread(target=self._load_weather, daemon=True).start()
        threading.Thread(target=self._load_calendar, daemon=True).start()

    # ── Export / Import ───────────────────────────────────────────────────────

    _BACKUP_FILES = [
        (os.path.expanduser("~/.config/morning-dashboard/prefs.json"),          "prefs.json"),
        (os.path.expanduser("~/.config/morning-dashboard/spurgeon_notes.json"), "spurgeon_notes.json"),
        (os.path.expanduser("~/.config/morning-dashboard/notes.txt"),           "notes.txt"),
        (os.path.join(PROJECT_DIR, "prayers.json"),                             "prayers.json"),
    ]

    def _export_data(self, btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Export personal data backup")
        today = datetime.date.today().strftime("%Y-%m-%d")
        dialog.set_initial_name(f"morning-dashboard-{today}.zip")
        f = Gtk.FileFilter()
        f.set_name("ZIP archive")
        f.add_pattern("*.zip")
        fl = Gio.ListStore.new(Gtk.FileFilter)
        fl.append(f)
        dialog.set_filters(fl)
        dialog.save(self, None, self._export_data_finish)

    def _export_data_finish(self, dialog, result):
        try:
            file = dialog.save_finish(result)
        except Exception:
            return
        if not file:
            return
        path = file.get_path()
        try:
            sermons_dir = os.path.expanduser("~/.config/morning-dashboard/sermons")
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for src, arcname in self._BACKUP_FILES:
                    if os.path.exists(src):
                        zf.write(src, arcname)
                if os.path.isdir(sermons_dir):
                    for fname in os.listdir(sermons_dir):
                        if fname.endswith(".txt"):
                            zf.write(os.path.join(sermons_dir, fname), f"sermons/{fname}")
            if hasattr(self, "_backup_status"):
                self._backup_status.set_text(f"✅ Exported to {os.path.basename(path)}")
        except Exception as e:
            if hasattr(self, "_backup_status"):
                self._backup_status.set_text(f"❌ Export failed: {e}")

    def _import_data(self, btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Import personal data backup")
        f = Gtk.FileFilter()
        f.set_name("ZIP archive")
        f.add_pattern("*.zip")
        fl = Gio.ListStore.new(Gtk.FileFilter)
        fl.append(f)
        dialog.set_filters(fl)
        dialog.open(self, None, self._import_data_finish)

    def _import_data_finish(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except Exception:
            return
        if not file:
            return
        path = file.get_path()
        dest_map = {arcname: src for src, arcname in self._BACKUP_FILES}
        sermons_dir = os.path.expanduser("~/.config/morning-dashboard/sermons")
        try:
            with zipfile.ZipFile(path, "r") as zf:
                for name in zf.namelist():
                    if name in dest_map:
                        dest = dest_map[name]
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with zf.open(name) as src, open(dest, "wb") as dst:
                            dst.write(src.read())
                    elif name.startswith("sermons/") and name.endswith(".txt"):
                        os.makedirs(sermons_dir, exist_ok=True)
                        fname = os.path.basename(name)
                        with zf.open(name) as src, open(os.path.join(sermons_dir, fname), "wb") as dst:
                            dst.write(src.read())
            self._refresh_sermon_list()
            self._spurgeon_notes_load()
            if hasattr(self, "_backup_status"):
                self._backup_status.set_text("✅ Imported — restart the app to apply all changes")
        except Exception as e:
            if hasattr(self, "_backup_status"):
                self._backup_status.set_text(f"❌ Import failed: {e}")

    def _backup_to_drive(self, btn):
        if not os.path.exists(CREDENTIALS):
            self._backup_status.set_text("❌ credentials.json not found in ~/morning-dashboard/")
            return
        self._backup_status.set_text("Starting backup…")
        def run():
            state = {"ok": True}
            def cb(msg):
                if msg.startswith("❌"):
                    state["ok"] = False
                GLib.idle_add(self._backup_status.set_text, msg)
            sermons_dir = os.path.expanduser("~/.config/morning-dashboard/sermons")
            sync_sermons_to_drive(sermons_dir, cb)
            if state["ok"]:
                sync_data_to_drive(cb)
            if state["ok"]:
                GLib.idle_add(self._backup_status.set_text, "✅ All backed up to Drive!")
        threading.Thread(target=run, daemon=True).start()

    # ── Spurgeon Tab ──────────────────────────────────────────────────────────

    def _build_spurgeon_tab(self):
        self._spurgeon_date = datetime.date.today()
        self._spurgeon_notes_file = os.path.expanduser(
            "~/.config/morning-dashboard/spurgeon_notes.json"
        )
        self._spurgeon_notes_save_id = None
        self._spurgeon_notes_loading = False

        # ── Left pane: devotional reading ────────────────────────────────────
        left_scroll = Gtk.ScrolledWindow()
        left_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("tab-content")
        box.set_spacing(8)

        spurgeon_title = Gtk.Label(label="Spurgeon's Morning and Evening")
        spurgeon_title.add_css_class("section-title")
        spurgeon_title.set_halign(Gtk.Align.START)
        box.append(spurgeon_title)

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

        self._spurgeon_modernise_btn = Gtk.Button(label="✨ Modernise")
        self._spurgeon_modernise_btn.add_css_class("sermon-btn")
        self._spurgeon_modernise_btn.set_tooltip_text("Generate a modern-English version using the Claude API")
        self._spurgeon_modernise_btn.connect("clicked", self._spurgeon_modernise)
        toolbar.append(self._spurgeon_modernise_btn)

        self._spurgeon_copy_btn = Gtk.Button(label="📋 Copy for Claude")
        self._spurgeon_copy_btn.add_css_class("sermon-btn")
        self._spurgeon_copy_btn.set_tooltip_text(
            "Copy a prompt to paste into Claude (no API key needed)"
        )
        self._spurgeon_copy_btn.connect("clicked", self._spurgeon_copy_for_claude)
        toolbar.append(self._spurgeon_copy_btn)

        self._spurgeon_paste_btn = Gtk.Button(label="📥 Paste result")
        self._spurgeon_paste_btn.add_css_class("sermon-btn")
        self._spurgeon_paste_btn.set_tooltip_text("Paste Claude's reply from the clipboard")
        self._spurgeon_paste_btn.connect("clicked", self._spurgeon_paste_result)
        toolbar.append(self._spurgeon_paste_btn)

        box.append(toolbar)

        # ── Original / Modern version toggle ───────────────────────────────
        self._spurgeon_version = "original"
        version_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        version_toolbar.add_css_class("sermon-toolbar")

        self._spurgeon_version_original_btn = Gtk.Button(label="Original")
        self._spurgeon_version_original_btn.add_css_class("sermon-btn")
        self._spurgeon_version_original_btn.add_css_class("suggested-action")
        self._spurgeon_version_original_btn.connect(
            "clicked", lambda b: self._spurgeon_set_version("original")
        )
        version_toolbar.append(self._spurgeon_version_original_btn)

        self._spurgeon_version_modern_btn = Gtk.Button(label="✨ Modern")
        self._spurgeon_version_modern_btn.add_css_class("sermon-btn")
        self._spurgeon_version_modern_btn.connect(
            "clicked", lambda b: self._spurgeon_set_version("modern")
        )
        version_toolbar.append(self._spurgeon_version_modern_btn)

        version_toolbar.set_visible(False)
        self._spurgeon_version_toolbar = version_toolbar
        box.append(version_toolbar)

        self._spurgeon_links = []  # list of (start_offset, end_offset, book_idx, chapter)

        self.spurgeon_buffer = Gtk.TextBuffer()
        self.spurgeon_buffer.create_tag("bold", weight=Pango.Weight.BOLD)
        self.spurgeon_buffer.create_tag("heading", weight=Pango.Weight.BOLD,
                                        scale=1.2)
        self.spurgeon_buffer.create_tag("normal")
        self.spurgeon_buffer.create_tag(
            "link",
            weight=Pango.Weight.BOLD,
            underline=Pango.Underline.SINGLE,
            foreground="#5599ff",
        )

        self.spurgeon_view = Gtk.TextView(buffer=self.spurgeon_buffer)
        self.spurgeon_view.set_editable(False)
        self.spurgeon_view.set_cursor_visible(False)
        self.spurgeon_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.spurgeon_view.set_left_margin(12)
        self.spurgeon_view.set_right_margin(12)
        self.spurgeon_view.set_top_margin(10)
        self.spurgeon_view.set_bottom_margin(10)
        self.spurgeon_view.add_css_class("reading-text")

        self._spurgeon_focus_gained = False
        self._spurgeon_press_pos = None
        focus_ctrl = Gtk.EventControllerFocus.new()
        focus_ctrl.connect("enter", lambda c: setattr(self, '_spurgeon_focus_gained', True))
        self.spurgeon_view.add_controller(focus_ctrl)

        click = Gtk.GestureClick.new()
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._spurgeon_link_clicked)
        click.connect("released", self._spurgeon_click_released)
        self.spurgeon_view.add_controller(click)

        motion = Gtk.EventControllerMotion.new()
        motion.connect("motion", self._spurgeon_motion)
        self.spurgeon_view.add_controller(motion)
        self.spurgeon_buffer.set_text("Loading today's reading…")

        box.append(self.spurgeon_view)

        # ── Modern English version (generated via Claude) ─────────────────────
        self._spurgeon_modern_current = None
        self._spurgeon_pending_refs = None  # {"date": ..., "am": (quote, ref), "pm": (quote, ref)}
        self._spurgeon_modern_revealer = Gtk.Revealer()
        self._spurgeon_modern_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._spurgeon_modern_revealer.set_reveal_child(False)

        modern_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        modern_box.set_margin_top(8)

        modern_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        modern_header.add_css_class("sermon-toolbar")
        modern_title = Gtk.Label(label="✨ Modern English")
        modern_title.add_css_class("section-title")
        modern_title.set_halign(Gtk.Align.START)
        modern_title.set_hexpand(True)
        modern_header.append(modern_title)

        self._spurgeon_modern_save_status = Gtk.Label(label="")
        self._spurgeon_modern_save_status.add_css_class("date-label")
        modern_header.append(self._spurgeon_modern_save_status)

        self._spurgeon_modern_edit_btn = Gtk.Button(label="✏️ Edit")
        self._spurgeon_modern_edit_btn.add_css_class("sermon-btn")
        self._spurgeon_modern_edit_btn.set_tooltip_text("Edit the modern English text")
        self._spurgeon_modern_edit_btn.set_visible(False)
        self._spurgeon_modern_edit_btn.connect("clicked", self._spurgeon_modern_enter_edit)
        modern_header.append(self._spurgeon_modern_edit_btn)

        self._spurgeon_modern_push_btn = Gtk.Button(label="📤 Push to web")
        self._spurgeon_modern_push_btn.add_css_class("sermon-btn")
        self._spurgeon_modern_push_btn.set_tooltip_text("Save and push this modernised version to the web app")
        self._spurgeon_modern_push_btn.connect("clicked", self._spurgeon_modern_push)
        modern_header.append(self._spurgeon_modern_push_btn)

        modern_box.append(modern_header)

        self._spurgeon_modern_links = []  # list of (start_offset, end_offset, book_idx, chapter)

        self.spurgeon_modern_buffer = Gtk.TextBuffer()
        self.spurgeon_modern_buffer.create_tag("bold", weight=Pango.Weight.BOLD)
        self.spurgeon_modern_buffer.create_tag("normal")
        self.spurgeon_modern_buffer.create_tag(
            "link",
            weight=Pango.Weight.BOLD,
            underline=Pango.Underline.SINGLE,
            foreground="#5599ff",
        )

        self.spurgeon_modern_view = Gtk.TextView(buffer=self.spurgeon_modern_buffer)
        self.spurgeon_modern_view.set_editable(False)
        self.spurgeon_modern_view.set_cursor_visible(False)
        self.spurgeon_modern_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.spurgeon_modern_view.set_left_margin(12)
        self.spurgeon_modern_view.set_right_margin(12)
        self.spurgeon_modern_view.set_top_margin(10)
        self.spurgeon_modern_view.set_bottom_margin(10)
        self.spurgeon_modern_view.add_css_class("reading-text")

        self._spurgeon_modern_focus_gained = False
        self._spurgeon_modern_press_pos = None
        modern_focus_ctrl = Gtk.EventControllerFocus.new()
        modern_focus_ctrl.connect("enter", lambda c: setattr(self, '_spurgeon_modern_focus_gained', True))
        self.spurgeon_modern_view.add_controller(modern_focus_ctrl)

        modern_click = Gtk.GestureClick.new()
        modern_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        modern_click.connect("pressed", self._spurgeon_modern_link_clicked)
        modern_click.connect("released", self._spurgeon_modern_click_released)
        self.spurgeon_modern_view.add_controller(modern_click)

        modern_motion = Gtk.EventControllerMotion.new()
        modern_motion.connect("motion", self._spurgeon_modern_motion)
        self.spurgeon_modern_view.add_controller(modern_motion)

        self._spurgeon_modern_stack = Gtk.Stack()
        self._spurgeon_modern_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self._spurgeon_modern_stack.add_named(self.spurgeon_modern_view, "view")

        # Edit page: two editable textviews for AM and PM
        edit_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        am_label = Gtk.Label(label="☀️ Morning")
        am_label.add_css_class("section-title")
        am_label.set_halign(Gtk.Align.START)
        am_label.set_margin_start(4)
        edit_page.append(am_label)

        self._spurgeon_edit_am_buf = Gtk.TextBuffer()
        self._spurgeon_edit_am_view = Gtk.TextView(buffer=self._spurgeon_edit_am_buf)
        self._spurgeon_edit_am_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self._spurgeon_edit_am_view.set_left_margin(8)
        self._spurgeon_edit_am_view.set_right_margin(8)
        self._spurgeon_edit_am_view.set_top_margin(6)
        self._spurgeon_edit_am_view.set_bottom_margin(6)
        self._spurgeon_edit_am_view.add_css_class("reading-text")
        am_scroll = Gtk.ScrolledWindow()
        am_scroll.set_vexpand(True)
        am_scroll.set_child(self._spurgeon_edit_am_view)
        edit_page.append(am_scroll)

        pm_label = Gtk.Label(label="🌙 Evening")
        pm_label.add_css_class("section-title")
        pm_label.set_halign(Gtk.Align.START)
        pm_label.set_margin_start(4)
        edit_page.append(pm_label)

        self._spurgeon_edit_pm_buf = Gtk.TextBuffer()
        self._spurgeon_edit_pm_view = Gtk.TextView(buffer=self._spurgeon_edit_pm_buf)
        self._spurgeon_edit_pm_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self._spurgeon_edit_pm_view.set_left_margin(8)
        self._spurgeon_edit_pm_view.set_right_margin(8)
        self._spurgeon_edit_pm_view.set_top_margin(6)
        self._spurgeon_edit_pm_view.set_bottom_margin(6)
        self._spurgeon_edit_pm_view.add_css_class("reading-text")
        pm_scroll = Gtk.ScrolledWindow()
        pm_scroll.set_vexpand(True)
        pm_scroll.set_child(self._spurgeon_edit_pm_view)
        edit_page.append(pm_scroll)

        edit_btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        edit_btn_row.add_css_class("sermon-toolbar")
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("sermon-btn")
        save_btn.connect("clicked", self._spurgeon_modern_save_edit)
        edit_btn_row.append(save_btn)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("sermon-btn")
        cancel_btn.connect("clicked", lambda b: self._spurgeon_modern_exit_edit())
        edit_btn_row.append(cancel_btn)
        edit_page.append(edit_btn_row)

        self._spurgeon_modern_stack.add_named(edit_page, "edit")
        modern_box.append(self._spurgeon_modern_stack)
        self._spurgeon_modern_revealer.set_child(modern_box)
        box.append(self._spurgeon_modern_revealer)

        left_scroll.set_child(box)

        # ── Right pane: date-keyed notes ──────────────────────────────────────
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        right_box.add_css_class("tab-content")
        right_box.set_spacing(6)

        notes_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.spurgeon_notes_date_label = Gtk.Label(
            label="Notes — " + datetime.date.today().strftime("%A, %d %B %Y")
        )
        self.spurgeon_notes_date_label.add_css_class("section-title")
        self.spurgeon_notes_date_label.set_halign(Gtk.Align.START)
        self.spurgeon_notes_date_label.set_hexpand(True)
        notes_header.append(self.spurgeon_notes_date_label)

        export_btn = Gtk.Button(label="Export all…")
        export_btn.add_css_class("sermon-btn")
        export_btn.connect("clicked", self._spurgeon_notes_export)
        notes_header.append(export_btn)

        right_box.append(notes_header)

        notes_scroll = Gtk.ScrolledWindow()
        notes_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        notes_scroll.set_size_request(-1, 140)

        self.spurgeon_notes_view = StyledTextView()
        self.spurgeon_notes_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.spurgeon_notes_view.add_css_class("bible-verse")
        self.spurgeon_notes_view.add_css_class("spurgeon-notes")
        self.spurgeon_notes_view.set_left_margin(8)
        self.spurgeon_notes_view.set_right_margin(8)
        self.spurgeon_notes_view.set_top_margin(8)
        self.spurgeon_notes_view.set_bottom_margin(8)
        self.spurgeon_notes_view.get_buffer().connect(
            "changed", self._spurgeon_notes_on_change
        )
        self.spurgeon_notes_view.connect("map", lambda w: w.grab_focus())
        _snv_rgba = Gdk.RGBA()
        _snv_rgba.parse("#d4a96a")
        self.spurgeon_notes_view.set_cursor_rgba(_snv_rgba)

        notes_scroll.set_child(self.spurgeon_notes_view)
        right_box.append(notes_scroll)

        # ── Community comments ────────────────────────────────────────────────
        right_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        comments_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        comments_header.set_margin_top(4)
        comm_lbl = Gtk.Label(label="Community Comments")
        comm_lbl.add_css_class("section-title")
        comm_lbl.set_halign(Gtk.Align.START)
        comm_lbl.set_hexpand(True)
        comments_header.append(comm_lbl)
        refresh_comm_btn = Gtk.Button(label="↻")
        refresh_comm_btn.add_css_class("sermon-btn")
        refresh_comm_btn.set_tooltip_text("Refresh comments")
        refresh_comm_btn.connect("clicked", lambda b: self._spurgeon_comments_load())
        comments_header.append(refresh_comm_btn)
        right_box.append(comments_header)

        self._spurgeon_comments_scroll = Gtk.ScrolledWindow()
        self._spurgeon_comments_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._spurgeon_comments_scroll.set_vexpand(True)
        self._spurgeon_comments_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._spurgeon_comments_box.set_margin_top(4)
        self._spurgeon_comments_box.set_margin_bottom(4)
        self._spurgeon_comments_scroll.set_child(self._spurgeon_comments_box)
        right_box.append(self._spurgeon_comments_scroll)

        comment_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        comment_row.set_margin_top(4)
        self._spurgeon_comment_entry = Gtk.Entry()
        self._spurgeon_comment_entry.set_placeholder_text("Add a comment…")
        self._spurgeon_comment_entry.set_hexpand(True)
        self._spurgeon_comment_entry.connect("activate", self._spurgeon_comment_post)
        comment_row.append(self._spurgeon_comment_entry)
        post_btn = Gtk.Button(label="Post")
        post_btn.add_css_class("sermon-btn")
        post_btn.connect("clicked", self._spurgeon_comment_post)
        comment_row.append(post_btn)
        right_box.append(comment_row)

        # ── Paned container ───────────────────────────────────────────────────
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_wide_handle(True)
        paned.set_start_child(left_scroll)
        paned.set_end_child(right_box)
        paned.set_position(self.spurgeon_paned_position)
        paned.set_resize_start_child(True)
        paned.set_shrink_start_child(False)
        paned.set_resize_end_child(True)
        paned.set_shrink_end_child(False)
        self._spurgeon_paned_save_id = None
        paned.connect("notify::position", self._spurgeon_paned_position_changed)

        self.stack.add_named(paned, "spurgeon")

        self._spurgeon_notes_load()
        self._spurgeon_comments_load()
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
        date_str = self._spurgeon_date.strftime("%A, %d %B %Y")
        self.spurgeon_date_label.set_text(date_str)
        self.spurgeon_notes_date_label.set_text("Notes — " + date_str)
        self.spurgeon_buffer.set_text("Loading…")
        self._spurgeon_modern_current = None
        self._spurgeon_show_modern(False)
        self._spurgeon_version_toolbar.set_visible(False)
        self._spurgeon_version_modern_btn.set_sensitive(False)
        self.spurgeon_modern_buffer.set_text("")
        self._spurgeon_modern_save_status.set_text("")
        self._spurgeon_modern_stack.set_visible_child_name("view")
        self._spurgeon_modern_push_btn.set_sensitive(True)
        self._spurgeon_notes_load()
        self._spurgeon_comments_load()
        threading.Thread(target=self._load_spurgeon, daemon=True).start()

    def _load_spurgeon(self):
        date = self._spurgeon_date
        text = fetch_spurgeon(date)
        cache = load_spurgeon_cache()
        cached = cache.get(date.isoformat())
        GLib.idle_add(self._set_spurgeon, date, text, cached)

    def _set_spurgeon(self, date, text, cached=None):
        import re
        if date != self._spurgeon_date:
            return
        self.spurgeon_buffer.set_text("")
        self._spurgeon_links = []
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
                    # Bold the verse reference (first line of rest) and hyperlink it
                    verse_end = rest.find("\n")
                    end = self.spurgeon_buffer.get_end_iter()
                    if verse_end > 0:
                        verse_ref = rest[:verse_end]
                        start_off = self.spurgeon_buffer.get_end_iter().get_offset()
                        self.spurgeon_buffer.insert_with_tags_by_name(end, verse_ref, "bold")
                        end_off = self.spurgeon_buffer.get_end_iter().get_offset()
                        s_it = self.spurgeon_buffer.get_iter_at_offset(start_off)
                        e_it = self.spurgeon_buffer.get_iter_at_offset(end_off)
                        self.spurgeon_buffer.apply_tag_by_name("link", s_it, e_it)
                        ref = self._parse_spurgeon_ref(verse_ref)
                        if ref:
                            self._spurgeon_links.append((start_off, end_off, ref[0], ref[1]))
                        end = self.spurgeon_buffer.get_end_iter()
                        self.spurgeon_buffer.insert_with_tags_by_name(end, "\n\n", "bold")
                        end = self.spurgeon_buffer.get_end_iter()
                        self.spurgeon_buffer.insert_with_tags_by_name(
                            end, rest[verse_end:].strip(), "normal"
                        )
                    else:
                        self.spurgeon_buffer.insert_with_tags_by_name(
                            end, rest, "normal"
                        )
                else:
                    # Format: "<quote>" Book Chapter:Verse. rest of text
                    ref_m = re.search(
                        r'"([^"]+)"\s+'
                        r'((?:\d+\s+)?[A-Z][a-z]+(?:\s+(?:of|the)\s+[A-Z][a-z]+)?'
                        r'\s+\d+:\d+[-\d–]*)'
                        r'\.',
                        body
                    )
                    if ref_m:
                        pre = body[:ref_m.start(2)]
                        verse_ref = ref_m.group(2)
                        post = body[ref_m.end():]
                        self.spurgeon_buffer.insert_with_tags_by_name(end, pre, "normal")
                        start_off = self.spurgeon_buffer.get_end_iter().get_offset()
                        end = self.spurgeon_buffer.get_end_iter()
                        self.spurgeon_buffer.insert_with_tags_by_name(end, verse_ref, "bold")
                        end_off = self.spurgeon_buffer.get_end_iter().get_offset()
                        s_it = self.spurgeon_buffer.get_iter_at_offset(start_off)
                        e_it = self.spurgeon_buffer.get_iter_at_offset(end_off)
                        self.spurgeon_buffer.apply_tag_by_name("link", s_it, e_it)
                        ref = self._parse_spurgeon_ref(verse_ref)
                        if ref:
                            self._spurgeon_links.append((start_off, end_off, ref[0], ref[1]))
                        end = self.spurgeon_buffer.get_end_iter()
                        self.spurgeon_buffer.insert_with_tags_by_name(end, "." + post, "normal")
                    else:
                        self.spurgeon_buffer.insert_with_tags_by_name(end, body, "normal")

        if cached:
            self._spurgeon_modern_current = cached
            self._render_spurgeon_modern(cached)
            self._spurgeon_version_toolbar.set_visible(True)
            self._spurgeon_version_modern_btn.set_sensitive(True)
        else:
            self._spurgeon_modern_current = None
            self.spurgeon_modern_buffer.set_text("")
            self._spurgeon_version_toolbar.set_visible(False)
            self._spurgeon_version_modern_btn.set_sensitive(False)

    def _spurgeon_show_modern(self, show):
        self._spurgeon_version = "modern" if show else "original"
        self.spurgeon_view.set_visible(not show)
        self._spurgeon_modern_revealer.set_reveal_child(show)
        self._spurgeon_modern_edit_btn.set_visible(show)
        for btn, active in (
            (self._spurgeon_version_original_btn, not show),
            (self._spurgeon_version_modern_btn, show),
        ):
            if active:
                btn.add_css_class("suggested-action")
            else:
                btn.remove_css_class("suggested-action")

    def _spurgeon_set_version(self, version):
        if version == "modern" and not self._spurgeon_modern_current:
            return
        if version == self._spurgeon_version:
            return
        self._spurgeon_show_modern(version == "modern")

    def _spurgeon_modern_enter_edit(self, btn=None):
        sections = self._spurgeon_modern_current or {"am": "", "pm": ""}
        self._spurgeon_edit_am_buf.set_text(sections.get("am", ""))
        self._spurgeon_edit_pm_buf.set_text(sections.get("pm", ""))
        self._spurgeon_modern_stack.set_visible_child_name("edit")
        self._spurgeon_modern_edit_btn.set_visible(False)
        self._spurgeon_modern_push_btn.set_sensitive(False)
        self._spurgeon_edit_am_view.grab_focus()

    def _spurgeon_modern_exit_edit(self):
        self._spurgeon_modern_stack.set_visible_child_name("view")
        self._spurgeon_modern_edit_btn.set_visible(True)
        self._spurgeon_modern_push_btn.set_sensitive(True)

    def _spurgeon_modern_save_edit(self, btn=None):
        am = self._spurgeon_edit_am_buf.get_text(
            self._spurgeon_edit_am_buf.get_start_iter(),
            self._spurgeon_edit_am_buf.get_end_iter(),
            False,
        )
        pm = self._spurgeon_edit_pm_buf.get_text(
            self._spurgeon_edit_pm_buf.get_start_iter(),
            self._spurgeon_edit_pm_buf.get_end_iter(),
            False,
        )
        self._spurgeon_modern_current = {"am": am, "pm": pm}
        self._render_spurgeon_modern(self._spurgeon_modern_current)
        self._spurgeon_modern_exit_edit()

    def _render_spurgeon_modern(self, sections):
        buf = self.spurgeon_modern_buffer
        buf.set_text("")
        self._spurgeon_modern_links = []
        for label, key in [("☀️ Morning", "am"), ("🌙 Evening", "pm")]:
            text = (sections.get(key) or "").strip()
            if not text:
                continue
            end = buf.get_end_iter()
            buf.insert_with_tags_by_name(end, label + "\n\n", "bold")

            # Leading '"<verse text>" <Reference>.' — show verse text in full,
            # bold/link the reference, then the modernised reflection.
            quote, ref, rest = extract_spurgeon_verse(text)
            if quote and ref:
                end = buf.get_end_iter()
                buf.insert_with_tags_by_name(end, f'"{quote}" ', "normal")
                start_off = buf.get_end_iter().get_offset()
                end = buf.get_end_iter()
                ref_match = self._parse_spurgeon_ref(ref)
                buf.insert_with_tags_by_name(end, ref, "link" if ref_match else "bold")
                end_off = buf.get_end_iter().get_offset()
                if ref_match:
                    self._spurgeon_modern_links.append((start_off, end_off, ref_match[0], ref_match[1]))
                end = buf.get_end_iter()
                buf.insert_with_tags_by_name(end, ".\n\n", "normal")
            else:
                rest = text

            if rest:
                end = buf.get_end_iter()
                buf.insert_with_tags_by_name(end, rest + "\n\n", "normal")

    def _spurgeon_modernise(self, btn):
        api_key = self.claude_api_key.strip()
        if not api_key:
            self.spurgeon_modern_buffer.set_text(
                "Add a Claude API key in Settings to use this feature."
            )
            self._spurgeon_version_toolbar.set_visible(True)
            self._spurgeon_show_modern(True)
            return
        date = self._spurgeon_date
        btn.set_sensitive(False)
        self.spurgeon_modern_buffer.set_text("Generating modern English version…")
        self._spurgeon_modern_save_status.set_text("")
        self._spurgeon_version_toolbar.set_visible(True)
        self._spurgeon_show_modern(True)
        threading.Thread(
            target=self._spurgeon_modernise_thread, args=(date, api_key), daemon=True
        ).start()

    def _spurgeon_modernise_thread(self, date, api_key):
        try:
            am_text, pm_text = split_spurgeon_sections(fetch_spurgeon(date))
            sections = modernize_spurgeon(am_text, pm_text, api_key)
        except Exception as e:
            GLib.idle_add(self._spurgeon_modernise_failed, date, str(e))
            return
        GLib.idle_add(self._spurgeon_modernise_done, date, sections)

    def _spurgeon_modernise_done(self, date, sections):
        self._spurgeon_modernise_btn.set_sensitive(True)
        if date != self._spurgeon_date:
            return
        self._spurgeon_modern_current = sections
        self._render_spurgeon_modern(sections)
        self._spurgeon_version_modern_btn.set_sensitive(True)

    def _spurgeon_modernise_failed(self, date, error):
        self._spurgeon_modernise_btn.set_sensitive(True)
        if date != self._spurgeon_date:
            return
        self.spurgeon_modern_buffer.set_text(f"Could not generate modern version: {error}")

    def _spurgeon_copy_for_claude(self, btn):
        date = self._spurgeon_date
        btn.set_sensitive(False)
        threading.Thread(
            target=self._spurgeon_copy_for_claude_thread, args=(date,), daemon=True
        ).start()

    def _spurgeon_copy_for_claude_thread(self, date):
        am_text, pm_text = split_spurgeon_sections(fetch_spurgeon(date))
        am_quote, am_ref, am_reflection = extract_spurgeon_verse(am_text)
        pm_quote, pm_ref, pm_reflection = extract_spurgeon_verse(pm_text)
        prompt = build_modernise_prompt(am_reflection, pm_reflection)
        refs = {"date": date, "am": (am_quote, am_ref), "pm": (pm_quote, pm_ref)}
        GLib.idle_add(self._spurgeon_copy_for_claude_done, refs, prompt)

    def _spurgeon_copy_for_claude_done(self, refs, prompt):
        self._spurgeon_copy_btn.set_sensitive(True)
        self._spurgeon_pending_refs = refs
        Gdk.Display.get_default().get_clipboard().set(prompt)
        self._spurgeon_modern_save_status.set_text(
            "📋 Copied — paste into Claude, then use 📥 Paste result"
        )
        GLib.timeout_add_seconds(5, self._spurgeon_modern_save_status_clear)

    def _spurgeon_paste_result(self, btn):
        Gdk.Display.get_default().get_clipboard().read_text_async(
            None, self._spurgeon_paste_result_done
        )

    def _spurgeon_paste_result_done(self, clipboard, result):
        try:
            reply = clipboard.read_text_finish(result)
        except Exception as e:
            self.spurgeon_modern_buffer.set_text(f"Could not read clipboard: {e}")
            self._spurgeon_version_toolbar.set_visible(True)
            self._spurgeon_show_modern(True)
            return
        if not reply:
            return
        am_modern, pm_modern = parse_modernise_reply(reply)
        refs = self._spurgeon_pending_refs
        if refs and refs["date"] == self._spurgeon_date:
            am_quote, am_ref = refs["am"]
            pm_quote, pm_ref = refs["pm"]
        else:
            am_quote = am_ref = pm_quote = pm_ref = ""
        sections = {
            "am": combine_spurgeon_modern(am_quote, am_ref, am_modern),
            "pm": combine_spurgeon_modern(pm_quote, pm_ref, pm_modern),
        }
        self._spurgeon_modern_current = sections
        self._render_spurgeon_modern(sections)
        self._spurgeon_version_toolbar.set_visible(True)
        self._spurgeon_version_modern_btn.set_sensitive(True)
        self._spurgeon_show_modern(True)
        self._spurgeon_modern_save_status.set_text("")

    def _spurgeon_modern_push(self, btn):
        if not self._spurgeon_modern_current:
            return
        if not self.web_url:
            self._spurgeon_modern_save_status.set_text("❌ No web app URL configured in settings.")
            return
        cache = load_spurgeon_cache()
        cache[self._spurgeon_date.isoformat()] = self._spurgeon_modern_current
        save_spurgeon_cache(cache)
        date = self._spurgeon_date
        sections = self._spurgeon_modern_current
        self._spurgeon_modern_save_status.set_text("Pushing…")

        def run():
            try:
                r = requests.post(
                    _normalize_url(self.web_url) + "/api/spurgeon_modern.php",
                    json={"date": date.isoformat(), "am": sections.get("am", ""), "pm": sections.get("pm", "")},
                    auth=(self.web_user, self.web_pass),
                    timeout=10,
                )
                if r.ok:
                    GLib.idle_add(self._spurgeon_modern_push_done, "✅ Saved & pushed to web app")
                else:
                    GLib.idle_add(self._spurgeon_modern_push_done, f"❌ Server returned {r.status_code}.")
            except Exception as e:
                GLib.idle_add(self._spurgeon_modern_push_done, f"❌ {e}")
        threading.Thread(target=run, daemon=True).start()

    def _spurgeon_modern_push_done(self, message):
        self._spurgeon_modern_save_status.set_text(message)
        GLib.timeout_add_seconds(2, self._spurgeon_modern_save_status_clear)

    def _spurgeon_modern_save_status_clear(self):
        self._spurgeon_modern_save_status.set_text("")
        return False

    def _spurgeon_paned_position_changed(self, paned, _pspec):
        if self._spurgeon_paned_save_id is not None:
            GLib.source_remove(self._spurgeon_paned_save_id)
        self._spurgeon_paned_save_id = GLib.timeout_add(
            500, self._spurgeon_paned_position_save, paned
        )

    def _spurgeon_paned_position_save(self, paned):
        self._spurgeon_paned_save_id = None
        self.spurgeon_paned_position = paned.get_position()
        self.prefs["spurgeon_paned_position"] = self.spurgeon_paned_position
        save_prefs(self.prefs)
        return False

    def _parse_spurgeon_ref(self, text):
        import re
        m = re.match(r'^(.+?)\s+(\d+)(?::\d+[\d–-]*)?', text.strip())
        if not m:
            return None
        book_str = m.group(1).strip().lower()
        chapter = int(m.group(2))
        aliases = {
            "psalm": "psalms",
            "song of songs": "song of solomon",
            "song": "song of solomon",
            "the song of solomon": "song of solomon",
            "revelation of john": "revelation",
        }
        book_str = aliases.get(book_str, book_str)
        for idx, (name, _, max_ch) in enumerate(BIBLE_BOOKS):
            if name.lower() == book_str:
                return (idx, min(chapter, max_ch))
        # prefix fallback
        for idx, (name, _, max_ch) in enumerate(BIBLE_BOOKS):
            if name.lower().startswith(book_str) or book_str.startswith(name.lower()):
                return (idx, min(chapter, max_ch))
        return None

    def _spurgeon_link_clicked(self, gesture, n_press, x, y):
        self._spurgeon_press_pos = (x, y)
        bx, by = self.spurgeon_view.window_to_buffer_coords(
            Gtk.TextWindowType.WIDGET, int(x), int(y)
        )
        ok, it = self.spurgeon_view.get_iter_at_location(bx, by)
        if not ok:
            return
        link_tag = self.spurgeon_buffer.get_tag_table().lookup("link")
        if not it.has_tag(link_tag):
            return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        offset = it.get_offset()
        for start_off, end_off, book_idx, chapter in self._spurgeon_links:
            if start_off <= offset < end_off:
                self._open_bible_ref(book_idx, chapter)
                break

    def _spurgeon_click_released(self, gesture, n_press, x, y):
        if not (self._spurgeon_focus_gained and n_press == 1):
            return
        self._spurgeon_focus_gained = False
        press = self._spurgeon_press_pos
        if press is None or (abs(x - press[0]) < 8 and abs(y - press[1]) < 8):
            it = self.spurgeon_buffer.get_iter_at_mark(self.spurgeon_buffer.get_insert())
            self.spurgeon_buffer.place_cursor(it)

    def _spurgeon_motion(self, controller, x, y):
        bx, by = self.spurgeon_view.window_to_buffer_coords(
            Gtk.TextWindowType.WIDGET, int(x), int(y)
        )
        ok, it = self.spurgeon_view.get_iter_at_location(bx, by)
        link_tag = self.spurgeon_buffer.get_tag_table().lookup("link")
        if ok and it.has_tag(link_tag):
            cursor = Gdk.Cursor.new_from_name("pointer", None)
        else:
            cursor = Gdk.Cursor.new_from_name("text", None)
        self.spurgeon_view.set_cursor(cursor)

    def _spurgeon_modern_link_clicked(self, gesture, n_press, x, y):
        self._spurgeon_modern_press_pos = (x, y)
        bx, by = self.spurgeon_modern_view.window_to_buffer_coords(
            Gtk.TextWindowType.WIDGET, int(x), int(y)
        )
        ok, it = self.spurgeon_modern_view.get_iter_at_location(bx, by)
        if not ok:
            return
        link_tag = self.spurgeon_modern_buffer.get_tag_table().lookup("link")
        if not it.has_tag(link_tag):
            return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        offset = it.get_offset()
        for start_off, end_off, book_idx, chapter in self._spurgeon_modern_links:
            if start_off <= offset < end_off:
                self._open_bible_ref(book_idx, chapter)
                break

    def _spurgeon_modern_click_released(self, gesture, n_press, x, y):
        if not (self._spurgeon_modern_focus_gained and n_press == 1):
            return
        self._spurgeon_modern_focus_gained = False
        press = self._spurgeon_modern_press_pos
        if press is None or (abs(x - press[0]) < 8 and abs(y - press[1]) < 8):
            it = self.spurgeon_modern_buffer.get_iter_at_mark(self.spurgeon_modern_buffer.get_insert())
            self.spurgeon_modern_buffer.place_cursor(it)

    def _spurgeon_modern_motion(self, controller, x, y):
        bx, by = self.spurgeon_modern_view.window_to_buffer_coords(
            Gtk.TextWindowType.WIDGET, int(x), int(y)
        )
        ok, it = self.spurgeon_modern_view.get_iter_at_location(bx, by)
        link_tag = self.spurgeon_modern_buffer.get_tag_table().lookup("link")
        if ok and it.has_tag(link_tag):
            cursor = Gdk.Cursor.new_from_name("pointer", None)
        else:
            cursor = Gdk.Cursor.new_from_name("text", None)
        self.spurgeon_modern_view.set_cursor(cursor)

    def _open_bible_ref(self, book_idx, chapter):
        self._switch_tab("bible")
        self.bible_book_combo.set_selected(book_idx)
        self.bible_chapter_spin.set_value(chapter)
        self._do_load_bible(book_idx, chapter)

    def _spurgeon_notes_export(self, btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Export Spurgeon notes")
        dialog.set_initial_name("spurgeon_notes.txt")
        f = Gtk.FileFilter()
        f.set_name("Text files")
        f.add_pattern("*.txt")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(f)
        dialog.set_filters(filters)
        dialog.save(self, None, self._spurgeon_notes_export_finish)

    def _spurgeon_notes_export_finish(self, dialog, result):
        try:
            file = dialog.save_finish(result)
        except Exception:
            return
        if not file:
            return
        try:
            with open(self._spurgeon_notes_file) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        lines = []
        for key in sorted(data.keys()):
            try:
                d = datetime.date.fromisoformat(key)
                heading = d.strftime("%A, %d %B %Y")
            except ValueError:
                heading = key
            lines.append(f"── {heading} ──\n")
            lines.append(data[key].strip())
            lines.append("\n\n")
        path = file.get_path()
        with open(path, "w") as f:
            f.write("\n".join(lines).strip() + "\n")

    def _spurgeon_notes_key(self):
        return self._spurgeon_date.isoformat()

    def _spurgeon_notes_load(self):
        self._spurgeon_notes_loading = True
        try:
            with open(self._spurgeon_notes_file) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        text = data.get(self._spurgeon_notes_key(), "")
        self.spurgeon_notes_view.get_buffer().set_text(text)
        self._spurgeon_notes_loading = False

    def _spurgeon_notes_on_change(self, buf):
        if self._spurgeon_notes_loading:
            return
        if self._spurgeon_notes_save_id is not None:
            GLib.source_remove(self._spurgeon_notes_save_id)
        self._spurgeon_notes_save_id = GLib.timeout_add(1000, self._spurgeon_notes_save)

    def _spurgeon_notes_save(self):
        self._spurgeon_notes_save_id = None
        buf = self.spurgeon_notes_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        try:
            with open(self._spurgeon_notes_file) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if text:
            data[self._spurgeon_notes_key()] = text
        else:
            data.pop(self._spurgeon_notes_key(), None)
        os.makedirs(os.path.dirname(self._spurgeon_notes_file), exist_ok=True)
        with open(self._spurgeon_notes_file, "w") as f:
            json.dump(data, f, indent=2)
        return False

    # ── Spurgeon community comments ───────────────────────────────────────────

    def _spurgeon_comments_load(self):
        if not self.web_url:
            GLib.idle_add(self._spurgeon_comments_render, None)
            return
        date_str = self._spurgeon_date.strftime("%Y-%m-%d")
        def run():
            try:
                r = requests.get(
                    _normalize_url(self.web_url) + "/api/spurgeon_comments.php",
                    params={"date": date_str},
                    auth=(self.web_user, self.web_pass),
                    timeout=10,
                )
                if r.ok:
                    result = r.json().get("comments", [])
                else:
                    result = f"Server returned HTTP {r.status_code}"
            except Exception as e:
                result = str(e)
            GLib.idle_add(self._spurgeon_comments_render, result)
        threading.Thread(target=run, daemon=True).start()

    def _spurgeon_comments_render(self, comments):
        child = self._spurgeon_comments_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._spurgeon_comments_box.remove(child)
            child = nxt

        if comments is None:
            lbl = Gtk.Label(label="Configure web app URL in Settings to see community comments.")
            lbl.add_css_class("status-label")
            lbl.set_wrap(True)
            lbl.set_xalign(0)
            self._spurgeon_comments_box.append(lbl)
            return

        if isinstance(comments, str):
            lbl = Gtk.Label(label=f"❌ {comments}")
            lbl.add_css_class("status-label")
            lbl.set_wrap(True)
            lbl.set_xalign(0)
            self._spurgeon_comments_box.append(lbl)
            return

        if not comments:
            lbl = Gtk.Label(label="No comments yet — be the first!")
            lbl.add_css_class("status-label")
            lbl.set_xalign(0)
            self._spurgeon_comments_box.append(lbl)
            return

        for c in comments:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.add_css_class("spur-comment-card")
            card.set_margin_start(4)
            card.set_margin_end(4)

            header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

            user_lbl = Gtk.Label(label=c.get("username", "?"))
            user_lbl.add_css_class("spur-comment-text")
            user_lbl.set_halign(Gtk.Align.START)
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
            user_lbl.set_attributes(attrs)
            header_row.append(user_lbl)

            ts = c.get("timestamp", 0)
            try:
                ts_str = datetime.datetime.fromtimestamp(ts).strftime("%d %b %Y %H:%M")
            except Exception:
                ts_str = ""
            ts_lbl = Gtk.Label(label=ts_str)
            ts_lbl.add_css_class("spur-comment-ts")
            ts_lbl.set_halign(Gtk.Align.START)
            ts_lbl.set_hexpand(True)
            header_row.append(ts_lbl)

            del_btn = Gtk.Button(label="✕")
            del_btn.add_css_class("sermon-btn")
            del_btn.set_tooltip_text("Delete comment")
            cid = c.get("id", "")
            del_btn.connect("clicked", lambda b, _id=cid: self._spurgeon_comment_delete(_id))
            header_row.append(del_btn)

            card.append(header_row)

            text_lbl = Gtk.Label(label=c.get("text", ""))
            text_lbl.add_css_class("spur-comment-text")
            text_lbl.set_wrap(True)
            text_lbl.set_xalign(0)
            text_lbl.set_halign(Gtk.Align.FILL)
            card.append(text_lbl)

            self._spurgeon_comments_box.append(card)

    def _spurgeon_comment_post(self, widget):
        text = self._spurgeon_comment_entry.get_text().strip()
        if not text or not self.web_url:
            return
        self._spurgeon_comment_entry.set_text("")
        date_str = self._spurgeon_date.strftime("%Y-%m-%d")
        def run():
            try:
                r = requests.post(
                    _normalize_url(self.web_url) + "/api/spurgeon_comments.php",
                    json={"date": date_str, "text": text},
                    auth=(self.web_user, self.web_pass),
                    timeout=10,
                )
                if r.ok:
                    GLib.idle_add(self._spurgeon_comments_load)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def _spurgeon_comment_delete(self, comment_id):
        if not self.web_url:
            return
        date_str = self._spurgeon_date.strftime("%Y-%m-%d")
        def run():
            try:
                r = requests.delete(
                    _normalize_url(self.web_url) + "/api/spurgeon_comments.php",
                    json={"date": date_str, "id": comment_id},
                    auth=(self.web_user, self.web_pass),
                    timeout=10,
                )
                if r.ok:
                    GLib.idle_add(self._spurgeon_comments_load)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    # ── Systematics Tab ──────────────────────────────────────────────────────

    def _build_systematics_tab(self):
        self._systematics_date = datetime.date.today()

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        # Centred column (mirrors web's .systematics-pane max-width:800px;margin:0 auto)
        clamp = Gtk.CenterBox()
        clamp.set_hexpand(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("tab-content")
        box.set_spacing(8)
        box.set_halign(Gtk.Align.CENTER)
        box.set_hexpand(False)
        box.set_size_request(800, -1)

        title = Gtk.Label(label="A Year in Systematic Theology")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        box.append(title)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.add_css_class("sermon-toolbar")

        prev_btn = Gtk.Button(label="◀ Prev")
        prev_btn.add_css_class("sermon-btn")
        prev_btn.connect("clicked", self._systematics_prev)
        toolbar.append(prev_btn)

        self.systematics_date_label = Gtk.Label(
            label=datetime.date.today().strftime("%A, %d %B %Y")
        )
        self.systematics_date_label.add_css_class("section-title")
        self.systematics_date_label.set_hexpand(True)
        self.systematics_date_label.set_halign(Gtk.Align.CENTER)
        toolbar.append(self.systematics_date_label)

        next_btn = Gtk.Button(label="Next ▶")
        next_btn.add_css_class("sermon-btn")
        next_btn.connect("clicked", self._systematics_next)
        toolbar.append(next_btn)

        today_btn = Gtk.Button(label="Today")
        today_btn.add_css_class("sermon-btn")
        today_btn.connect("clicked", self._systematics_today)
        toolbar.append(today_btn)

        box.append(toolbar)

        jump_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        jump_toolbar.add_css_class("sermon-toolbar")

        jump_label = Gtk.Label(label="Jump to:")
        jump_label.add_css_class("section-title")
        jump_toolbar.append(jump_label)

        division_names = [label for _, label in SYSTEMATICS_DIVISIONS]
        self._systematics_jump_combo = Gtk.DropDown.new_from_strings(division_names)
        self._systematics_jump_combo.set_hexpand(True)
        self._systematics_jump_combo.connect("notify::selected", self._systematics_jump)
        jump_toolbar.append(self._systematics_jump_combo)

        box.append(jump_toolbar)

        dark = self.theme == "dark"
        quote_bg = "#16213e" if dark else "#e8eaf2"  # matches web's --header-bg used for .systematics-verse

        self.systematics_buffer = Gtk.TextBuffer()
        self.systematics_buffer.create_tag("bold", weight=Pango.Weight.BOLD)
        self.systematics_buffer.create_tag("heading", weight=Pango.Weight.BOLD, scale=1.2)
        self.systematics_buffer.create_tag("normal")
        self.systematics_buffer.create_tag("italic", style=Pango.Style.ITALIC)
        self.systematics_buffer.create_tag(
            "label", foreground="#7e57c2", weight=Pango.Weight.BOLD, scale=0.85,
        )
        self.systematics_buffer.create_tag(
            "verse",
            paragraph_background=quote_bg,
            left_margin=24, right_margin=16,
            pixels_above_lines=8, pixels_below_lines=8,
        )

        self.systematics_view = Gtk.TextView(buffer=self.systematics_buffer)
        self.systematics_view.set_editable(False)
        self.systematics_view.set_cursor_visible(False)
        self.systematics_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.systematics_view.set_left_margin(12)
        self.systematics_view.set_right_margin(12)
        self.systematics_view.set_top_margin(10)
        self.systematics_view.set_bottom_margin(10)
        self.systematics_view.add_css_class("reading-text")
        self.systematics_buffer.set_text("Loading today's reading…")

        box.append(self.systematics_view)
        clamp.set_center_widget(box)
        scroll.set_child(clamp)

        self.stack.add_named(scroll, "systematics")

        threading.Thread(target=self._load_systematics, daemon=True).start()

    def _systematics_prev(self, btn):
        self._systematics_date -= datetime.timedelta(days=1)
        self._systematics_refresh()

    def _systematics_next(self, btn):
        self._systematics_date += datetime.timedelta(days=1)
        self._systematics_refresh()

    def _systematics_today(self, btn):
        self._systematics_date = datetime.date.today()
        self._systematics_refresh()

    def _systematics_jump(self, dropdown, pspec):
        idx = dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(SYSTEMATICS_DIVISIONS):
            return
        day, _label = SYSTEMATICS_DIVISIONS[idx]
        # day-of-year -> month/day via the same fixed non-leap reference year
        # used by api/systematics.php, then applied to the year currently in view.
        ref = datetime.date(2025, 1, 1) + datetime.timedelta(days=day - 1)
        self._systematics_date = datetime.date(self._systematics_date.year, ref.month, ref.day)
        self._systematics_refresh()

    def _systematics_refresh(self):
        self.systematics_date_label.set_text(self._systematics_date.strftime("%A, %d %B %Y"))
        self.systematics_buffer.set_text("Loading…")
        threading.Thread(target=self._load_systematics, daemon=True).start()

    def _load_systematics(self):
        date = self._systematics_date
        if not self.web_url:
            GLib.idle_add(self._set_systematics, date, None)
            return
        try:
            r = requests.get(
                _normalize_url(self.web_url) + "/api/systematics.php",
                params={"date": date.isoformat()},
                auth=(self.web_user, self.web_pass),
                timeout=10,
            )
            if r.ok:
                result = r.json()
            else:
                result = f"Server returned HTTP {r.status_code}"
        except Exception as e:
            result = str(e)
        GLib.idle_add(self._set_systematics, date, result)

    def _set_systematics(self, date, result):
        if date != self._systematics_date:
            return
        self.systematics_buffer.set_text("")
        end = self.systematics_buffer.get_end_iter()

        if result is None:
            self.systematics_buffer.insert_with_tags_by_name(
                end, "Configure a web app URL in Settings to view this devotional.", "normal"
            )
            return
        if isinstance(result, str):
            self.systematics_buffer.insert_with_tags_by_name(end, f"Could not load reading: {result}", "normal")
            return
        if not result.get("available"):
            day = result.get("day", "?")
            self.systematics_buffer.insert_with_tags_by_name(
                end, f"Day {day} — this devotional hasn't been written yet.", "normal"
            )
            return

        sections = result.get("sections", {})
        end = self.systematics_buffer.get_end_iter()
        self.systematics_buffer.insert_with_tags_by_name(end, result.get("section", "").upper() + "\n", "label")
        end = self.systematics_buffer.get_end_iter()
        self.systematics_buffer.insert_with_tags_by_name(end, result.get("title", "") + "\n\n", "heading")

        for key in ["Verse", "Explanation", "Prayer", "Reflection Question"]:
            body = sections.get(key)
            if not body:
                continue
            end = self.systematics_buffer.get_end_iter()
            self.systematics_buffer.insert_with_tags_by_name(end, key.upper() + "\n", "label")
            self._systematics_insert_body(body, extra_tag="verse" if key == "Verse" else None)
            end = self.systematics_buffer.get_end_iter()
            self.systematics_buffer.insert(end, "\n\n")

    def _systematics_insert_body(self, text, extra_tag=None):
        """Insert plain text, rendering *word* spans in italics."""
        import re
        extras = [extra_tag] if extra_tag else []
        pos = 0
        for m in re.finditer(r'\*(.+?)\*', text):
            end = self.systematics_buffer.get_end_iter()
            self.systematics_buffer.insert_with_tags_by_name(end, text[pos:m.start()], *extras, "normal")
            end = self.systematics_buffer.get_end_iter()
            self.systematics_buffer.insert_with_tags_by_name(end, m.group(1), *extras, "italic")
            pos = m.end()
        end = self.systematics_buffer.get_end_iter()
        self.systematics_buffer.insert_with_tags_by_name(end, text[pos:], *extras, "normal")

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
        self.stack.add_named(scroll, "news")

        threading.Thread(target=self._load_news, daemon=True).start()

    def _load_news(self):
        all_items = {}
        for source, url, proxy in NEWS_SOURCES:
            all_items[source] = fetch_news_proxied(url) if proxy else fetch_news(url)
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

        self.weather_icon_lbl = Gtk.Label(label="🌡️")
        self.weather_icon_lbl.add_css_class("weather-icon")
        current_box.append(self.weather_icon_lbl)

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
        self.forecast_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.forecast_box.set_spacing(8)
        self.forecast_box.set_homogeneous(True)
        self.weather_outer.append(self.forecast_box)

        note = Gtk.Label(label="Weather powered by Open-Meteo (no API key needed)")
        note.add_css_class("date-label")
        note.set_halign(Gtk.Align.CENTER)
        self.weather_outer.append(note)

        scroll.set_child(self.weather_outer)
        self.stack.add_named(scroll, "weather")
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
                    GLib.idle_add(self._set_weather, "--°C", "🌡️",
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
            icon = self._weather_icon(code)
            current_str = f"{self._weather_desc(code)}  —  {city}"

            # Build 7-day list
            daily = w.get("daily", {})
            dates    = daily.get("time", [])
            codes    = daily.get("weathercode", [])
            maxtemps = daily.get("temperature_2m_max", [])
            mintemps = daily.get("temperature_2m_min", [])

            forecast = []
            for i in range(min(7, len(dates))):
                date_obj = datetime.date.fromisoformat(dates[i])
                day_name = date_obj.strftime("%A")
                fi       = self._weather_icon(codes[i]) if codes else "?"
                hi       = f"{maxtemps[i]:.0f}°" if maxtemps else "--"
                lo       = f"{mintemps[i]:.0f}°" if mintemps else "--"
                forecast.append((day_name, fi, hi, lo))

            GLib.idle_add(self._set_weather, f"{temp}°C", icon, current_str, forecast)
        except Exception as e:
            GLib.idle_add(self._set_weather, "--°C", "🌡️",
                          f"Could not load weather: {e}", [])

    def _set_weather(self, temp, icon, desc, forecast):
        self.weather_icon_lbl.set_text(icon)
        self.weather_temp.set_text(temp)
        self.weather_desc.set_text(desc)

        # Clear old forecast rows
        child = self.forecast_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.forecast_box.remove(child)
            child = nxt

        # Add new forecast cards
        for day_name, icon, hi, lo in forecast:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.add_css_class("forecast-card")
            card.set_hexpand(True)

            day_lbl = Gtk.Label(label=day_name[:3])  # Mon, Tue, etc.
            day_lbl.add_css_class("forecast-day")
            day_lbl.set_halign(Gtk.Align.CENTER)

            icon_lbl = Gtk.Label(label=icon)
            icon_lbl.add_css_class("forecast-icon")
            icon_lbl.set_halign(Gtk.Align.CENTER)

            hi_lbl = Gtk.Label(label=hi)
            hi_lbl.add_css_class("forecast-hi")
            hi_lbl.set_halign(Gtk.Align.CENTER)

            lo_lbl = Gtk.Label(label=lo)
            lo_lbl.add_css_class("forecast-lo")
            lo_lbl.set_halign(Gtk.Align.CENTER)

            card.append(day_lbl)
            card.append(icon_lbl)
            card.append(hi_lbl)
            card.append(lo_lbl)
            self.forecast_box.append(card)

    def _weather_icon(self, code):
        icons = {
            0: "☀️",  1: "🌤️",  2: "⛅",   3: "☁️",
            45: "🌫️", 48: "🌫️",
            51: "🌦️", 53: "🌦️", 55: "🌧️",
            61: "🌧️", 63: "🌧️", 65: "🌧️",
            71: "❄️",  73: "❄️",  75: "❄️",  77: "🌨️",
            80: "🌦️", 81: "🌦️", 82: "🌧️",
            85: "🌨️", 86: "🌨️",
            95: "⛈️", 96: "⛈️", 99: "⛈️",
        }
        return icons.get(code, "🌡️")

    def _weather_desc(self, code):
        descs = {
            0: "Clear sky",       1: "Mainly clear",    2: "Partly cloudy",
            3: "Overcast",        45: "Foggy",           48: "Icy fog",
            51: "Light drizzle",  53: "Drizzle",         55: "Heavy drizzle",
            61: "Light rain",     63: "Rain",            65: "Heavy rain",
            71: "Light snow",     73: "Snow",            75: "Heavy snow",
            77: "Snow grains",    80: "Showers",         81: "Showers",
            82: "Heavy showers",  85: "Snow showers",    86: "Heavy snow showers",
            95: "Thunderstorm",   96: "Thunderstorm",    99: "Thunderstorm",
        }
        return descs.get(code, f"Code {code}")


    # ── Sermon Notes Tab ──────────────────────────────────────────────────────

    def _build_sermon_tab(self):
        SERMONS_DIR = os.path.expanduser("~/.config/morning-dashboard/sermons")
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

        # Web sync toolbar
        web_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        web_toolbar.add_css_class("sermon-toolbar")

        web_sync_btn = Gtk.Button(label="⇅ Sync with web")
        web_sync_btn.add_css_class("sermon-btn")
        web_sync_btn.connect("clicked", lambda b: self._sermon_sync_web())
        web_toolbar.append(web_sync_btn)

        right.append(web_toolbar)

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
        self.sermon_view = StyledTextView(buffer=self.sermon_buffer)
        self.sermon_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.sermon_view.set_left_margin(12)
        self.sermon_view.set_right_margin(12)
        self.sermon_view.set_top_margin(10)
        self.sermon_view.set_bottom_margin(10)
        self.sermon_view.add_css_class("reading-text")
        if hasattr(self, "_theme_cursor_rgba"):
            self.sermon_view.set_cursor_rgba(self._theme_cursor_rgba)

        scroll_text.set_child(self.sermon_view)
        right.append(scroll_text)

        outer.append(left)
        outer.append(right)

        self.stack.add_named(outer, "sermons")
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

        # Clean up old file if sermon is renamed
        if self.current_sermon_file and self.current_sermon_file != fname:
            old_path = os.path.join(self.sermons_dir, self.current_sermon_file)
            try:
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception:
                pass

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
        self.stack.add_named(scroll, "calendar")
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

    def _sermon_sync_web(self):
        if not self.web_url:
            GLib.idle_add(self.sync_status.set_text, "❌ No web app URL configured in settings.")
            return
        GLib.idle_add(self.sync_status.set_text, "Syncing sermons…")
        def run():
            try:
                base = _normalize_url(self.web_url) + "/api/sermons.php"
                auth = (self.web_user, self.web_pass)

                r = requests.get(base, auth=auth, timeout=10)
                if not r.ok:
                    GLib.idle_add(self.sync_status.set_text, f"❌ Server returned {r.status_code}.")
                    return
                data = r.json()
                web_files = set(data.get("sermons", []))
                web_mtimes = data.get("mtimes", {})

                local_files = {
                    f: os.path.getmtime(os.path.join(self.sermons_dir, f))
                    for f in os.listdir(self.sermons_dir) if f.endswith(".txt")
                }

                pushed = pulled = skipped = 0

                for fname in web_files | set(local_files):
                    local_path = os.path.join(self.sermons_dir, fname)
                    in_local = fname in local_files
                    in_web   = fname in web_files

                    if in_local and not in_web:
                        with open(local_path) as f:
                            text = f.read()
                        r2 = requests.post(base, json={"title": fname[:-4], "text": text}, auth=auth, timeout=15)
                        if not r2.ok:
                            GLib.idle_add(self.sync_status.set_text, f"❌ Failed pushing {fname}: {r2.status_code}")
                            return
                        pushed += 1

                    elif in_web and not in_local:
                        r2 = requests.get(base, params={"file": fname}, auth=auth, timeout=15)
                        if not r2.ok:
                            GLib.idle_add(self.sync_status.set_text, f"❌ Failed fetching {fname}: {r2.status_code}")
                            return
                        with open(local_path, "w") as f:
                            f.write(r2.json().get("text", ""))
                        pulled += 1

                    else:
                        r2 = requests.get(base, params={"file": fname}, auth=auth, timeout=15)
                        if not r2.ok:
                            GLib.idle_add(self.sync_status.set_text, f"❌ Failed fetching {fname}: {r2.status_code}")
                            return
                        web_text = r2.json().get("text", "")
                        with open(local_path) as f:
                            local_text = f.read()

                        if local_text == web_text:
                            skipped += 1
                            continue

                        if local_files[fname] >= web_mtimes.get(fname, 0):
                            r3 = requests.post(base, json={"title": fname[:-4], "text": local_text}, auth=auth, timeout=15)
                            if not r3.ok:
                                GLib.idle_add(self.sync_status.set_text, f"❌ Failed pushing {fname}: {r3.status_code}")
                                return
                            pushed += 1
                        else:
                            with open(local_path, "w") as f:
                                f.write(web_text)
                            pulled += 1

                GLib.idle_add(self._refresh_sermon_list)
                parts = []
                if pushed:  parts.append(f"{pushed} pushed")
                if pulled:  parts.append(f"{pulled} pulled")
                if skipped: parts.append(f"{skipped} unchanged")
                GLib.idle_add(self.sync_status.set_text,
                              "✅ Synced: " + (", ".join(parts) if parts else "nothing to do") + ".")
            except Exception as e:
                GLib.idle_add(self.sync_status.set_text, f"❌ {e}")
        threading.Thread(target=run, daemon=True).start()

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
        saved_book  = min(self.prefs.get("bible_book", 0), len(BIBLE_BOOKS) - 1)
        saved_ch    = self.prefs.get("bible_chapter", 1)
        saved_trans = min(self.prefs.get("bible_translation", 0), len(BIBLE_TRANSLATIONS) - 1)

        self._bible_book_idx    = saved_book
        self._bible_chapter     = saved_ch
        self._bible_translation = saved_trans

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("tab-content")
        outer.set_spacing(8)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.add_css_class("sermon-toolbar")

        # Translation dropdown
        trans_names = [t[0] for t in BIBLE_TRANSLATIONS]
        self.bible_trans_combo = Gtk.DropDown.new_from_strings(trans_names)
        self.bible_trans_combo.set_selected(saved_trans)
        toolbar.append(self.bible_trans_combo)

        # Book dropdown
        book_names = [b[0] for b in BIBLE_BOOKS]
        self.bible_book_combo = Gtk.DropDown.new_from_strings(book_names)
        self.bible_book_combo.set_selected(saved_book)
        self.bible_book_combo.connect("notify::selected", self._on_bible_book_changed)
        toolbar.append(self.bible_book_combo)

        # Chapter spinner — set range for saved book, then restore saved chapter
        self.bible_chapter_spin = Gtk.SpinButton()
        self.bible_chapter_spin.set_range(1, BIBLE_BOOKS[saved_book][2])
        self.bible_chapter_spin.set_increments(1, 5)
        self.bible_chapter_spin.set_value(saved_ch)
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

        mcheyne_btn = Gtk.MenuButton(label="M'Cheyne")
        mcheyne_btn.add_css_class("sermon-btn")
        mcheyne_btn.set_popover(self._build_mcheyne_popover())
        toolbar.append(mcheyne_btn)

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

        self.bible_citation_label = Gtk.Label()
        self.bible_citation_label.add_css_class("bible-citation")
        self.bible_citation_label.set_wrap(True)
        self.bible_citation_label.set_halign(Gtk.Align.START)
        self.bible_citation_label.set_margin_start(12)
        self.bible_citation_label.set_margin_end(12)
        self.bible_citation_label.set_margin_bottom(6)
        self.bible_citation_label.set_visible(False)
        outer.append(self.bible_citation_label)

        self.stack.add_named(outer, "bible")

        self._do_load_bible(saved_book, saved_ch)

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
        self.prefs["bible_book"] = book_idx
        self.prefs["bible_chapter"] = chapter
        self.prefs["bible_translation"] = trans_idx
        save_prefs(self.prefs)
        book_name, book_id, max_ch = BIBLE_BOOKS[book_idx]
        trans_name = BIBLE_TRANSLATIONS[trans_idx][0]
        trans_id   = BIBLE_TRANSLATIONS[trans_idx][1]
        self.bible_ref_label.set_text(f"{book_name} {chapter}  —  {trans_name}")
        self.bible_buffer.set_text("Loading…")
        if trans_id.startswith("apibible:"):
            bible_name = trans_id[len("apibible:"):]
            citation = _APIBIBLE_CITATIONS.get(bible_name, "")
            self.bible_citation_label.set_text(citation)
            self.bible_citation_label.set_visible(bool(citation))
        else:
            self.bible_citation_label.set_visible(False)
        threading.Thread(
            target=self._fetch_and_set_bible,
            args=(book_id, chapter, trans_id),
            daemon=True
        ).start()

    def _fetch_and_set_bible(self, book_id, chapter, trans_id):
        if trans_id.startswith("apibible:"):
            text = fetch_apibible_chapter(book_id, chapter, trans_id[len("apibible:"):], self.api_bible_key)
        else:
            text = fetch_esv_chapter(book_id, chapter, trans_id)
        GLib.idle_add(self._set_bible_text, text)

    def _set_bible_text(self, text):
        import re
        buf = self.bible_buffer
        buf.set_text("")
        tag_table = buf.get_tag_table()
        sup_tag = tag_table.lookup("verse-num")
        if sup_tag is None:
            sup_tag = buf.create_tag("verse-num", rise=6000, scale=0.72, foreground="#888888")
        pattern = re.compile(r'\[(\d+)\] ?')
        pos = 0
        for m in pattern.finditer(text):
            if m.start() > pos:
                buf.insert(buf.get_end_iter(), text[pos:m.start()])
            buf.insert_with_tags(buf.get_end_iter(), m.group(1), sup_tag)
            pos = m.end()
        if pos < len(text):
            buf.insert(buf.get_end_iter(), text[pos:])

    def _build_mcheyne_popover(self):
        today = datetime.date.today()
        readings = mcheyne_readings_for_date(today)
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        title = Gtk.Label(label=f"M'Cheyne — {today.strftime('%B %-d')}")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        box.append(title)
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(4)
        sep.set_margin_bottom(4)
        box.append(sep)
        for book_idx, chapter, book_name in readings:
            btn = Gtk.Button(label=f"{book_name} {chapter}")
            btn.add_css_class("sermon-btn")
            btn.connect("clicked", self._on_mcheyne_reading_clicked, popover, book_idx, chapter)
            box.append(btn)
        popover.set_child(box)
        return popover

    def _on_mcheyne_reading_clicked(self, _btn, popover, book_idx, chapter):
        popover.popdown()
        self._open_bible_ref(book_idx, chapter)

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
        PRAYER_FILE = os.path.join(PROJECT_DIR, "prayers.json")
        self.prayer_file = PRAYER_FILE
        self._prayer_adding_child_for = None

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("tab-content")
        outer.set_spacing(8)

        # Header row
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label="🙏  Prayer List")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)

        clear_btn = Gtk.Button(label="↺ Reset prayers")
        clear_btn.add_css_class("sermon-btn")
        clear_btn.connect("clicked", self._prayer_clear_done)
        header_row.append(title)
        header_row.append(clear_btn)
        outer.append(header_row)

        # Hall Green prayer diary banner
        try:
            diary_path = os.path.join(PROJECT_DIR, "prayer_diary.json")
            with open(diary_path) as _f:
                _diary = json.load(_f)
            _today = datetime.date.today()
            _day_num = min(_today.day, 30)
            _day_key = str(_day_num)
            _month_name = _today.strftime("%B")
            _diary_names = _diary.get("days", {}).get(_day_key, "")
            _diary_theme = _diary.get("monthly_themes", {}).get(_month_name, "")

            diary_banner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            diary_banner.add_css_class("prayer-diary-banner")
            diary_banner.set_margin_bottom(4)

            day_lbl = Gtk.Label(label=f"Day {_day_num}: {_diary_names}")
            day_lbl.add_css_class("prayer-diary-names")
            day_lbl.set_halign(Gtk.Align.START)
            day_lbl.set_wrap(True)
            diary_banner.append(day_lbl)

            if _diary_theme:
                theme_lbl = Gtk.Label(label=f"{_month_name}: {_diary_theme}")
                theme_lbl.add_css_class("prayer-diary-theme")
                theme_lbl.set_halign(Gtk.Align.START)
                theme_lbl.set_wrap(True)
                diary_banner.append(theme_lbl)

            outer.append(diary_banner)
        except Exception:
            pass

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

        self.stack.add_named(outer, "prayer")
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

    def _prayer_push_to_web(self, url, user, password, status_lbl):
        if not url:
            GLib.idle_add(status_lbl.set_text, "❌ No web app URL configured in settings.")
            return
        GLib.idle_add(status_lbl.set_text, "Pushing prayers…")
        def run():
            try:
                r = requests.post(
                    _normalize_url(url) + "/api/prayers.php",
                    json={"prayers": self.prayers},
                    auth=(user, password),
                    timeout=10,
                )
                if r.ok:
                    GLib.idle_add(status_lbl.set_text, "✅ Prayers pushed to web app.")
                else:
                    GLib.idle_add(status_lbl.set_text, f"❌ Server returned {r.status_code}.")
            except Exception as e:
                GLib.idle_add(status_lbl.set_text, f"❌ {e}")
        threading.Thread(target=run, daemon=True).start()

    def _prayer_pull_from_web(self, url, user, password, status_lbl):
        if not url:
            GLib.idle_add(status_lbl.set_text, "❌ No web app URL configured in settings.")
            return
        GLib.idle_add(status_lbl.set_text, "Pulling prayers…")
        def run():
            try:
                r = requests.get(
                    _normalize_url(url) + "/api/prayers.php",
                    auth=(user, password),
                    timeout=10,
                )
                if r.ok:
                    data = r.json()
                    prayers = data.get("prayers", [])
                    self.prayers = prayers
                    self._prayer_save()
                    GLib.idle_add(self._prayer_render)
                    GLib.idle_add(status_lbl.set_text, "✅ Prayers pulled from web app.")
                else:
                    GLib.idle_add(status_lbl.set_text, f"❌ Server returned {r.status_code}.")
            except Exception as e:
                GLib.idle_add(status_lbl.set_text, f"❌ {e}")
        threading.Thread(target=run, daemon=True).start()

    # ── Web App Admin ──────────────────────────────────────────────────────────

    def _admin_load_requests(self, url, user, password, requests_box, status_lbl):
        if not url:
            GLib.idle_add(status_lbl.set_text, "❌ No web app URL configured.")
            return
        GLib.idle_add(status_lbl.set_text, "Loading…")

        def run():
            try:
                r = requests.get(
                    _normalize_url(url) + "/api/access.php",
                    params={"action": "list"},
                    auth=(user, password),
                    timeout=10,
                )
                if r.status_code == 403:
                    GLib.idle_add(status_lbl.set_text, "❌ Not authorised (admin only).")
                    return
                if not r.ok:
                    GLib.idle_add(status_lbl.set_text, f"❌ Server returned {r.status_code}.")
                    return
                pending = [x for x in r.json().get("requests", []) if x.get("status") == "pending"]
                GLib.idle_add(self._admin_render_requests,
                              requests_box, status_lbl, pending, url, user, password)
            except Exception as e:
                GLib.idle_add(status_lbl.set_text, f"❌ {e}")

        threading.Thread(target=run, daemon=True).start()

    def _admin_render_requests(self, requests_box, status_lbl, pending, url, user, password):
        # Clear previous results
        child = requests_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            requests_box.remove(child)
            child = nxt

        if not pending:
            status_lbl.set_text("✅ No pending requests.")
            return

        n = len(pending)
        status_lbl.set_text(f"{n} pending request{'s' if n != 1 else ''}:")

        for req in pending:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.add_css_class("card-subtle")

            # Username + name
            top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            uname = Gtk.Label(label=req.get("username", ""))
            uname.set_markup(f"<b>{uname.get_text()}</b>")
            uname.set_halign(Gtk.Align.START)
            name_lbl = Gtk.Label(label=req.get("name", ""))
            name_lbl.add_css_class("date-label")
            name_lbl.set_halign(Gtk.Align.START)
            name_lbl.set_hexpand(True)
            top_row.append(uname)
            top_row.append(name_lbl)
            card.append(top_row)

            if req.get("reason"):
                reason_lbl = Gtk.Label(label=req["reason"])
                reason_lbl.add_css_class("date-label")
                reason_lbl.set_halign(Gtk.Align.START)
                reason_lbl.set_wrap(True)
                card.append(reason_lbl)

            date_lbl = Gtk.Label(label=req.get("requested", ""))
            date_lbl.add_css_class("date-label")
            date_lbl.set_halign(Gtk.Align.START)
            card.append(date_lbl)

            btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            btn_row.set_margin_top(4)
            approve_btn = Gtk.Button(label="✅ Approve")
            approve_btn.add_css_class("sermon-btn")
            deny_btn = Gtk.Button(label="✗ Deny")
            deny_btn.add_css_class("sermon-btn")
            result_lbl = Gtk.Label(label="")
            result_lbl.add_css_class("date-label")
            result_lbl.set_halign(Gtk.Align.START)
            result_lbl.set_hexpand(True)
            btn_row.append(approve_btn)
            btn_row.append(deny_btn)
            btn_row.append(result_lbl)
            card.append(btn_row)

            def _approve_cb(b, username=req["username"], a=approve_btn, d=deny_btn, rl=result_lbl):
                a.set_sensitive(False); d.set_sensitive(False)
                self._admin_approve(url, user, password, username, rl)

            def _deny_cb(b, username=req["username"], a=approve_btn, d=deny_btn, rl=result_lbl):
                a.set_sensitive(False); d.set_sensitive(False)
                self._admin_deny(url, user, password, username, rl)

            approve_btn.connect("clicked", _approve_cb)
            deny_btn.connect("clicked", _deny_cb)
            requests_box.append(card)

    def _admin_approve(self, url, user, password, username, result_lbl):
        GLib.idle_add(result_lbl.set_text, "Approving…")
        def run():
            try:
                r = requests.post(
                    _normalize_url(url) + "/api/access.php",
                    json={"action": "approve", "username": username},
                    auth=(user, password),
                    timeout=10,
                )
                data = r.json()
                if data.get("error"):
                    GLib.idle_add(result_lbl.set_text, f"❌ {data['error']}")
                elif data.get("user_set_password"):
                    GLib.idle_add(result_lbl.set_text, "✅ Approved — they can log in with their chosen password.")
                else:
                    pw = data.get("password", "")
                    GLib.idle_add(result_lbl.set_text, f"✅ Approved — password: {pw}")
            except Exception as e:
                GLib.idle_add(result_lbl.set_text, f"❌ {e}")
        threading.Thread(target=run, daemon=True).start()

    def _admin_deny(self, url, user, password, username, result_lbl):
        GLib.idle_add(result_lbl.set_text, "Denying…")
        def run():
            try:
                r = requests.post(
                    _normalize_url(url) + "/api/access.php",
                    json={"action": "deny", "username": username},
                    auth=(user, password),
                    timeout=10,
                )
                data = r.json()
                if data.get("ok"):
                    GLib.idle_add(result_lbl.set_text, "Denied.")
                else:
                    GLib.idle_add(result_lbl.set_text, f"❌ {data.get('error', 'Unknown error')}")
            except Exception as e:
                GLib.idle_add(result_lbl.set_text, f"❌ {e}")
        threading.Thread(target=run, daemon=True).start()

    def _prayer_render(self):
        child = self.prayer_list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.prayer_list_box.remove(child)
            child = nxt

        undone = [p for p in self.prayers if not p.get("done")]
        done   = [p for p in self.prayers if p.get("done")]

        for prayer in undone + done:
            self._prayer_add_row(prayer)
            for sub in prayer.get("children", []):
                if not sub.get("done"):
                    self._prayer_add_row(sub, parent=prayer, indented=True)
            if self._prayer_adding_child_for is prayer:
                self._prayer_child_entry_row(prayer)

    def _prayer_add_row(self, prayer, parent=None, indented=False):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        if indented:
            spacer = Gtk.Box()
            spacer.set_size_request(28, -1)
            row.append(spacer)

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

        lbl.set_cursor(Gdk.Cursor.new_from_name("text"))
        edit_gesture = Gtk.GestureClick()
        edit_gesture.connect("released", lambda g, n, x, y: self._prayer_start_edit(prayer, lbl, row))
        lbl.add_controller(edit_gesture)

        del_btn = Gtk.Button(label="✕")
        del_btn.add_css_class("sermon-btn")
        del_btn.connect("clicked", self._prayer_delete, prayer, parent)

        row.append(check)
        row.append(lbl)

        if not indented:
            if not prayer.get("done"):
                undone = [p for p in self.prayers if not p.get("done")]
                idx = undone.index(prayer)
                up_btn = Gtk.Button(label="▲")
                up_btn.add_css_class("sermon-btn")
                up_btn.set_sensitive(idx > 0)
                up_btn.connect("clicked", lambda b, p=prayer: self._prayer_move(p, -1))
                dn_btn = Gtk.Button(label="▼")
                dn_btn.add_css_class("sermon-btn")
                dn_btn.set_sensitive(idx < len(undone) - 1)
                dn_btn.connect("clicked", lambda b, p=prayer: self._prayer_move(p, 1))
                row.append(up_btn)
                row.append(dn_btn)
            sub_btn = Gtk.Button(label="+ sub")
            sub_btn.add_css_class("sermon-btn")
            sub_btn.connect("clicked", lambda b, p=prayer: self._prayer_start_add_child(p))
            row.append(sub_btn)

        row.append(del_btn)
        self.prayer_list_box.append(row)

    def _prayer_child_entry_row(self, parent_prayer):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spacer = Gtk.Box()
        spacer.set_size_request(28, -1)
        row.append(spacer)

        entry = Gtk.Entry()
        entry.set_placeholder_text("Name or request…")
        entry.set_hexpand(True)
        entry.add_css_class("sermon-title-entry")

        def confirm(_=None):
            text = entry.get_text().strip()
            if text:
                parent_prayer.setdefault("children", []).append({"text": text, "done": False})
                self._prayer_save()
            self._prayer_adding_child_for = None
            self._prayer_render()

        def cancel():
            self._prayer_adding_child_for = None
            self._prayer_render()

        key_ctrl = Gtk.EventControllerKey()
        def on_key(ctrl, keyval, keycode, state):
            if keyval == Gdk.KEY_Escape:
                cancel()
                return True
            return False
        key_ctrl.connect("key-pressed", on_key)
        entry.add_controller(key_ctrl)
        entry.connect("activate", confirm)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("sermon-btn")
        cancel_btn.connect("clicked", lambda b: cancel())

        ok_btn = Gtk.Button(label="Add")
        ok_btn.add_css_class("sermon-btn")
        ok_btn.connect("clicked", confirm)

        row.append(entry)
        row.append(cancel_btn)
        row.append(ok_btn)
        self.prayer_list_box.append(row)
        entry.grab_focus()

    def _prayer_start_edit(self, prayer, lbl, row):
        entry = Gtk.Entry()
        entry.set_text(prayer["text"])
        entry.set_hexpand(True)
        entry.add_css_class("sermon-title-entry")

        finished = [False]

        def finish(save):
            if finished[0]:
                return
            finished[0] = True
            if save:
                text = entry.get_text().strip()
                if text and text != prayer["text"]:
                    prayer["text"] = text
                    self._prayer_save()
            self._prayer_render()

        key_ctrl = Gtk.EventControllerKey()
        def on_key(ctrl, keyval, keycode, state):
            if keyval == Gdk.KEY_Escape:
                finish(False)
                return True
            return False
        key_ctrl.connect("key-pressed", on_key)
        entry.add_controller(key_ctrl)
        entry.connect("activate", lambda e: finish(True))

        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("leave", lambda c: finish(True))
        entry.add_controller(focus_ctrl)

        row.insert_child_after(entry, lbl)
        row.remove(lbl)
        entry.grab_focus()

    def _prayer_start_add_child(self, parent_prayer):
        self._prayer_adding_child_for = parent_prayer
        self._prayer_render()

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
        for child in prayer.get("children", []):
            child["done"] = prayer["done"]
        self._prayer_save()
        self._prayer_render()

    def _prayer_delete(self, btn, prayer, parent=None):
        if parent is None:
            self.prayers = [p for p in self.prayers if p is not prayer]
        else:
            parent["children"] = [c for c in parent.get("children", []) if c is not prayer]
        self._prayer_save()
        self._prayer_render()

    def _prayer_move(self, prayer, direction):
        undone = [p for p in self.prayers if not p.get("done")]
        done   = [p for p in self.prayers if p.get("done")]
        idx = undone.index(prayer)
        new_idx = idx + direction
        if 0 <= new_idx < len(undone):
            undone[idx], undone[new_idx] = undone[new_idx], undone[idx]
            self.prayers = undone + done
            self._prayer_save()
            self._prayer_render()

    def _prayer_clear_done(self, btn):
        for p in self.prayers:
            p["done"] = False
            for c in p.get("children", []):
                c["done"] = False
        self._prayer_save()
        self._prayer_render()

    # ── Notes tab ─────────────────────────────────────────────────────────────

    def _build_notes_tab(self):
        NOTES_FILE = os.path.expanduser("~/.config/morning-dashboard/notes.txt")
        self._notes_file = NOTES_FILE
        self._notes_save_id = None

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("tab-content")
        outer.set_spacing(8)

        title = Gtk.Label(label="📝  Notes")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        outer.append(title)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self.notes_view = StyledTextView()
        self.notes_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.notes_view.add_css_class("bible-verse")
        self.notes_view.set_left_margin(8)
        self.notes_view.set_right_margin(8)
        self.notes_view.set_top_margin(8)
        self.notes_view.set_bottom_margin(8)

        try:
            with open(NOTES_FILE) as f:
                self.notes_view.get_buffer().set_text(f.read())
        except FileNotFoundError:
            pass

        self.notes_view.get_buffer().connect("changed", self._notes_on_change)
        if hasattr(self, "_theme_cursor_rgba"):
            self.notes_view.set_cursor_rgba(self._theme_cursor_rgba)

        scroll.set_child(self.notes_view)
        outer.append(scroll)

        self.stack.add_named(outer, "notes")

    def _notes_on_change(self, buf):
        if self._notes_save_id is not None:
            GLib.source_remove(self._notes_save_id)
        self._notes_save_id = GLib.timeout_add(1000, self._notes_save)

    def _notes_save(self):
        self._notes_save_id = None
        buf = self.notes_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        os.makedirs(os.path.dirname(self._notes_file), exist_ok=True)
        with open(self._notes_file, "w") as f:
            f.write(text)
        return False

    def _spurgeon_notes_push_to_web(self, url, user, password, status_lbl):
        if not url:
            GLib.idle_add(status_lbl.set_text, "❌ No web app URL configured in settings.")
            return
        try:
            with open(self._spurgeon_notes_file) as f:
                notes = json.load(f)
        except Exception:
            notes = {}
        GLib.idle_add(status_lbl.set_text, "Pushing Spurgeon notes…")
        def run():
            try:
                r = requests.post(
                    _normalize_url(url) + "/api/spurgeon_notes.php",
                    json={"all": notes},
                    auth=(user, password),
                    timeout=10,
                )
                if r.ok:
                    GLib.idle_add(status_lbl.set_text, "✅ Spurgeon notes pushed to web app.")
                else:
                    GLib.idle_add(status_lbl.set_text, f"❌ Server returned {r.status_code}.")
            except Exception as e:
                GLib.idle_add(status_lbl.set_text, f"❌ {e}")
        threading.Thread(target=run, daemon=True).start()

    def _spurgeon_notes_pull_from_web(self, url, user, password, status_lbl):
        if not url:
            GLib.idle_add(status_lbl.set_text, "❌ No web app URL configured in settings.")
            return
        GLib.idle_add(status_lbl.set_text, "Pulling Spurgeon notes…")
        def run():
            try:
                r = requests.get(
                    _normalize_url(url) + "/api/spurgeon_notes.php",
                    params={"all": 1},
                    auth=(user, password),
                    timeout=10,
                )
                if r.ok:
                    notes = r.json().get("notes", {})
                    GLib.idle_add(self._spurgeon_notes_apply_pulled, notes)
                    GLib.idle_add(status_lbl.set_text, "✅ Spurgeon notes pulled from web app.")
                else:
                    GLib.idle_add(status_lbl.set_text, f"❌ Server returned {r.status_code}.")
            except Exception as e:
                GLib.idle_add(status_lbl.set_text, f"❌ {e}")
        threading.Thread(target=run, daemon=True).start()

    def _spurgeon_notes_apply_pulled(self, notes):
        os.makedirs(os.path.dirname(self._spurgeon_notes_file), exist_ok=True)
        with open(self._spurgeon_notes_file, "w") as f:
            json.dump(notes, f, indent=2)
        self._spurgeon_notes_load()

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
