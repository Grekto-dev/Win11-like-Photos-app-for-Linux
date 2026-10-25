#!/bin/bash
# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
#
# Builds dist/photos_<version>_all.deb from the working tree (version read from photos/__init__.py).
# Layout: /usr/lib/photos (code), /usr/bin/photos (symlink), desktop entry, icon, docs.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="$(python3 -c 'import re,sys; print(re.search(r"__version__ = \"([^\"]+)\"", open("photos/__init__.py").read()).group(1))')"
PKG="photos"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
DEB="dist/${PKG}_${VERSION}_all.deb"

install -d "$ROOT/DEBIAN" "$ROOT/usr/lib/photos/bin" "$ROOT/usr/lib/photos/data" "$ROOT/usr/bin" \
  "$ROOT/usr/share/applications" "$ROOT/usr/share/icons/hicolor/scalable/apps" "$ROOT/usr/share/doc/$PKG"

# application code (no caches, no test data)
cp -r photos "$ROOT/usr/lib/photos/photos"
find "$ROOT/usr/lib/photos" -name '__pycache__' -type d -prune -exec rm -rf {} +
install -m 0755 bin/photos "$ROOT/usr/lib/photos/bin/photos"
install -m 0644 data/photos.svg "$ROOT/usr/lib/photos/data/photos.svg"
ln -s ../lib/photos/bin/photos "$ROOT/usr/bin/photos"
install -m 0644 data/photos.svg "$ROOT/usr/share/icons/hicolor/scalable/apps/photos.svg"
install -m 0644 data/dev.grekto.Photos.desktop "$ROOT/usr/share/applications/dev.grekto.Photos.desktop"
install -m 0644 README.md docs/DESIGN-NOTES.md NOTICE "$ROOT/usr/share/doc/$PKG/"

cat > "$ROOT/usr/share/doc/$PKG/copyright" <<'CPR'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: Photos for Linux
Source: https://github.com/Grekto-dev/Win11-like-Photos-app-for-Linux

Files: *
Copyright: 2026 Grekto-dev
License: Apache-2.0

License: Apache-2.0
 Licensed under the Apache License, Version 2.0 (the "License"); you may not use
 this software except in compliance with the License. You may obtain a copy of
 the License at http://www.apache.org/licenses/LICENSE-2.0
 .
 On Debian systems, the complete text of the Apache License, Version 2.0 can be
 found in "/usr/share/common-licenses/Apache-2.0".
CPR

SIZE="$(du -sk "$ROOT/usr" | cut -f1)"
cat > "$ROOT/DEBIAN/control" <<CTL
Package: $PKG
Version: $VERSION
Section: graphics
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, python3-cairo, gir1.2-gtk-3.0, gir1.2-gdkpixbuf-2.0, gir1.2-pango-1.0, python3-pil, librsvg2-common
Recommends: ffmpegthumbnailer, gvfs
Replaces: fotos (<< 1.0.1)
Conflicts: fotos (<< 1.0.1)
Installed-Size: $SIZE
Maintainer: Grekto-dev <176182924+Grekto-dev@users.noreply.github.com>
Homepage: https://github.com/Grekto-dev/Win11-like-Photos-app-for-Linux
Description: Photo gallery, viewer and editor inspired by the Windows 11 Photos app
 Photos for Linux is an independent re-creation of the Windows 11 Photos app:
 a gallery with date grouping and favorites, an image viewer with smooth zoom,
 filmstrip and EXIF panel, a slideshow and a simple editor (crop, adjust,
 filters, markup). The interface is available in English, Portuguese (Brazil),
 Spanish, French, Chinese (Simplified), Hindi and Arabic.
CTL

cat > "$ROOT/DEBIAN/postinst" <<'PST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
  command -v python3 >/dev/null 2>&1 && python3 -m compileall -q /usr/lib/photos/photos >/dev/null 2>&1 || true
fi
exit 0
PST
cat > "$ROOT/DEBIAN/postrm" <<'PRM'
#!/bin/sh
set -e
case "$1" in
  remove|purge)
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
    rm -rf /usr/lib/photos 2>/dev/null || true ;;
esac
exit 0
PRM
chmod 0755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/postrm"

find "$ROOT" -type d -exec chmod 0755 {} +
find "$ROOT/usr" -type f ! -perm -u+x -exec chmod 0644 {} +
mkdir -p dist
fakeroot dpkg-deb --root-owner-group -Zxz --build "$ROOT" "$DEB" >/dev/null
sha256sum "$DEB" | sed "s#dist/##" > "$DEB.sha256"
echo "Built $DEB"
dpkg-deb --info "$DEB" | sed -n '1,14p'
