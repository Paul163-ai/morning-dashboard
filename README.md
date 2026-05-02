# ☀️ Morning Dashboard

A personal daily briefing app for the Linux desktop, built with Python and GTK4.

## Features

- 📖 Spurgeon Morning & Evening devotional
- 📰 News — BBC, AI & Tech headlines
- 🌤️ Weather — current conditions and 7-day forecast
- 📜 Bible reader — 10 translations, all 66 books
- ✍️ Sermon notes with Google Drive sync
- 📅 Google Calendar — 7-day view across all calendars
- 🙏 Prayer list with checkboxes
- ⚙️ Preferences — dark/light theme, font size, location search

## Requirements

- Linux with GTK4 (Linux Mint 22+, Ubuntu 24.04+)
- Python 3.10+

## Installation

```bash
git clone https://github.com/Paul163-ai/morning-dashboard.git
cd morning-dashboard
pip3 install requests google-auth google-auth-oauthlib google-api-python-client google-auth-httplib2 --break-system-packages
python3 dashboard.py
```

A setup wizard will guide you through the rest on first launch.

## Google Integration (optional)

Calendar and Drive sync require a free Google Cloud credentials file.
The setup wizard will guide you through getting one.

## License

GPL-2.0 — Paul Lintott
