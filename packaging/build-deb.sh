#!/usr/bin/env bash
# Builds tee-cell-stream-server_<version>_amd64.deb from this source tree.
#
#   bash packaging/build-deb.sh            -> dist/tee-cell-stream-server_<version>_amd64.deb
#   FFMPEG_BUNDLE=/path/to/ffmpeg bash packaging/build-deb.sh
#
# Python plus one binary: the patched ffmpeg (ffmpeg-nvenc/build-ffmpeg.sh builds it in Ubuntu 24.04, so it
# runs from glibc 2.38 on). Everything else (GStreamer, GTK4/libadwaita, evdev, portal) comes from the
# distribution via Depends, so `apt install ./tee-cell-stream-server_*.deb` is a one-click install.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="tee-cell-stream-server"
VERSION="$(python3 -c "import re,sys; print(re.search(r'__version__ = \"([^\"]+)\"', open('$ROOT/src/teecellstream/__init__.py').read()).group(1))")"
EPOCH="$(python3 -c "import re,sys; m=re.search(r'DEB_EPOCH = \"([^\"]+)\"', open('$ROOT/src/teecellstream/__init__.py').read()); print(m.group(1) if m else '')")"
# The epoch belongs in the control file, never in the file NAME: dpkg-deb writes a colon nowhere and
# a filename with one is a nuisance on every filesystem that has an opinion about them.
DEB_VERSION="${EPOCH:+$EPOCH:}$VERSION"
STAGE="$ROOT/build/pkgroot"
DIST="$ROOT/dist"
DEB="$DIST/${PKG}_${VERSION}_amd64.deb"
FFMPEG_BUNDLE="${FFMPEG_BUNDLE:-$ROOT/build-1.1.1/work/out/linux/ffmpeg}"
if [ ! -x "$FFMPEG_BUNDLE" ]; then
   echo "the patched ffmpeg is missing: $FFMPEG_BUNDLE (build it with ffmpeg-nvenc/build-ffmpeg.sh)" >&2
   exit 1
fi

echo "== $PKG $VERSION"
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$DIST"

# --- program -----------------------------------------------------------------------------------------
install -d "$STAGE/usr/lib/$PKG/teecellstream"
install -m 644 "$ROOT"/src/teecellstream/*.py "$STAGE/usr/lib/$PKG/teecellstream/"
install -d "$STAGE/usr/bin"
install -m 755 "$ROOT/packaging/launcher.sh" "$STAGE/usr/bin/$PKG"
# the patched ffmpeg, where ffmpeg_find.bundled_linux() looks: next to the package, not on PATH - it must
# never stand in for the distribution's ffmpeg in anybody else's program
install -D -m 755 "$FFMPEG_BUNDLE" "$STAGE/usr/lib/$PKG/ffmpeg/ffmpeg"

# --- desktop integration -----------------------------------------------------------------------------
install -d "$STAGE/usr/share/applications"
install -m 644 "$ROOT/data/$PKG.desktop" "$STAGE/usr/share/applications/"
if [ -d "$ROOT/data/icons/hicolor" ]; then
   (cd "$ROOT/data/icons/hicolor" && find . -type f -name '*.png' -o -type f -name '*.svg') | while read -r icon; do
      install -D -m 644 "$ROOT/data/icons/hicolor/$icon" "$STAGE/usr/share/icons/hicolor/$icon"
   done
fi

# --- virtual gamepad: /dev/uinput for the logged-in user, module at boot -----------------------------
install -D -m 644 "$ROOT/data/70-tee-cell-stream-uinput.rules" "$STAGE/usr/lib/udev/rules.d/70-tee-cell-stream-uinput.rules"
install -d "$STAGE/usr/lib/modules-load.d"
echo "uinput" > "$STAGE/usr/lib/modules-load.d/$PKG.conf"

# --- GNOME extension: keeps the capture alive while a game runs fullscreen -----------------------------
EXT_UUID="tee-cell-stream-scanout@tee.local"
install -d "$STAGE/usr/share/gnome-shell/extensions/$EXT_UUID"
install -m 644 "$ROOT/data/gnome-extension/metadata.json" "$ROOT/data/gnome-extension/extension.js" \
   "$STAGE/usr/share/gnome-shell/extensions/$EXT_UUID/"

# --- docs --------------------------------------------------------------------------------------------
# the German guide is what a user of this package reads; the English README is the repo's front page
install -D -m 644 "$ROOT/README.de.md" "$STAGE/usr/share/doc/$PKG/ANLEITUNG.md"
install -D -m 644 "$ROOT/README.md" "$STAGE/usr/share/doc/$PKG/README.md"
install -D -m 644 "$ROOT/packaging/copyright" "$STAGE/usr/share/doc/$PKG/copyright"
# Apache-2.0 section 4(d): the NOTICE file travels with every distribution of the work
install -D -m 644 "$ROOT/NOTICE" "$STAGE/usr/share/doc/$PKG/NOTICE"
# the bundled ffmpeg is GPL: where its source is and how it was built
install -D -m 644 "$ROOT/packaging/ffmpeg-README.txt" "$STAGE/usr/share/doc/$PKG/ffmpeg/README.txt"
install -D -m 644 "$ROOT/ffmpeg-nvenc/build-ffmpeg.sh" "$STAGE/usr/share/doc/$PKG/ffmpeg/build-ffmpeg.sh"
for patch in "$ROOT"/ffmpeg-nvenc/*.patch; do
   case "$(basename "$patch")" in nvenc-dblk_idc.patch) continue ;; esac   # superseded by the combined one
   install -D -m 644 "$patch" "$STAGE/usr/share/doc/$PKG/ffmpeg/$(basename "$patch")"
done
gzip -9 -n -c "$ROOT/packaging/changelog" > "$STAGE/usr/share/doc/$PKG/changelog.gz"
chmod 644 "$STAGE/usr/share/doc/$PKG/changelog.gz"

# --- control -----------------------------------------------------------------------------------------
INSTALLED_KB="$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)"
sed -e "s/@VERSION@/$DEB_VERSION/" -e "s/@INSTALLED_SIZE@/$INSTALLED_KB/" "$ROOT/packaging/control" > "$STAGE/DEBIAN/control"
for script in postinst prerm postrm; do
   install -m 755 "$ROOT/packaging/$script" "$STAGE/DEBIAN/$script"
done
(cd "$STAGE" && find usr -type f -exec md5sum {} \; > DEBIAN/md5sums)

find "$STAGE" -type d -exec chmod 755 {} \;
find "$STAGE/usr" -type f -exec chmod 644 {} \;
chmod 755 "$STAGE/usr/bin/$PKG" "$STAGE/usr/lib/$PKG/ffmpeg/ffmpeg"

rm -f "$DEB"
dpkg-deb --root-owner-group --build "$STAGE" "$DEB" >/dev/null
echo "== built: $DEB"
dpkg-deb --info "$DEB" | sed -n '1,25p'
if command -v lintian >/dev/null 2>&1; then
   echo "== lintian (informational)"
   lintian --no-tag-display-limit "$DEB" || true
fi
