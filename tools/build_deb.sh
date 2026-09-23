#!/usr/bin/env bash
# Build the desktop app .deb from the current working tree.
#
#   tools/build_deb.sh            -> ./morning-dashboard_YYYY.MM.DD_all.deb
#   tools/build_deb.sh 2026.10.01 -> explicit version
#
# Installs the app to /usr/lib/morning-dashboard with a /usr/bin launcher.
# User data never goes there (it's root-owned): dashboard.py falls back to
# ~/.local/share/morning-dashboard when its own directory isn't writable.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-$(date +%Y.%m.%d)}"
PKG=morning-dashboard
APPDIR=/usr/lib/$PKG
OUT="$REPO/${PKG}_${VERSION}_all.deb"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
# mktemp makes the dir 0700 and it becomes the package's "./" entry; also
# normalise modes so a permissive umask (e.g. 002) doesn't leak into the .deb.
chmod 755 "$STAGE"
umask 022

install -Dm755 "$REPO/dashboard.py" "$STAGE$APPDIR/dashboard.py"
install -Dm644 "$REPO/icon.png"     "$STAGE$APPDIR/icon.png"

install -d "$STAGE/usr/bin"
cat > "$STAGE/usr/bin/$PKG" <<EOF
#!/bin/sh
exec python3 $APPDIR/dashboard.py "\$@"
EOF
chmod 755 "$STAGE/usr/bin/$PKG"

install -d "$STAGE/usr/share/applications"
cat > "$STAGE/usr/share/applications/$PKG.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Morning Dashboard
Comment=Your daily briefing — devotional, news and weather
Exec=$PKG
Icon=$APPDIR/icon.png
Terminal=false
Categories=Utility;
StartupNotify=true
EOF

install -d "$STAGE/DEBIAN"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Architecture: all
Maintainer: Paul Lintott <paul.lintott@gmail.com>
Depends: python3, python3-gi, python3-requests, gir1.2-gtk-4.0
Recommends: python3-google-auth, python3-google-auth-oauthlib, python3-google-auth-httplib2, python3-googleapi
Description: Morning Dashboard
 GTK4 daily briefing app — Spurgeon devotional, news, weather,
 Bible, prayer, notes, sermons, and Google Calendar.
EOF

python3 -m py_compile "$STAGE$APPDIR/dashboard.py"
rm -rf "$STAGE$APPDIR/__pycache__"

dpkg-deb --root-owner-group --build "$STAGE" "$OUT" >/dev/null
echo "Built $OUT"
dpkg-deb -c "$OUT"
