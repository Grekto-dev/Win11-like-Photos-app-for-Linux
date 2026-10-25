#!/bin/bash
# Installs Photos for the current user (symlinks; use "--uninstall" to remove).
set -e
here="$(cd "$(dirname "$0")" && pwd)"
bin="$HOME/.local/bin"; apps="$HOME/.local/share/applications"; icons="$HOME/.local/share/icons/hicolor/scalable/apps"
if [ "$1" = "--uninstall" ]; then
  rm -f "$bin/photos" "$apps/dev.grekto.Photos.desktop" "$icons/photos.svg"
  update-desktop-database "$apps" 2>/dev/null || true
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
  echo "Removed."; exit 0
fi
mkdir -p "$bin" "$apps" "$icons"
ln -sf "$here/bin/photos" "$bin/photos"
ln -sf "$here/data/photos.svg" "$icons/photos.svg"
sed "s#^Exec=photos#Exec=$bin/photos#" "$here/data/dev.grekto.Photos.desktop" > "$apps/dev.grekto.Photos.desktop"
update-desktop-database "$apps" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
echo "Installed: $bin/photos (menu entry: Photos). To make it the default image viewer:"
echo "  xdg-mime default dev.grekto.Photos.desktop image/png image/jpeg image/webp image/gif image/bmp image/tiff"
