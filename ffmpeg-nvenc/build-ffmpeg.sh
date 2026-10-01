#!/bin/bash
# Builds the ffmpeg that TEE PS3 Remoteplay ships, for Linux and for Windows, from:
#
#   ffmpeg 8.0.1            https://ffmpeg.org/releases/ffmpeg-8.0.1.tar.xz (release key FCF986EA15E6E293A5644F10B4322F04D67658D8)
#   + two patches           patches/nvenc-dblk_idc-mv_precision.patch, patches/mpeg2-intra-refresh.patch
#   x264 r3222 b35605a      https://code.videolan.org/videolan/x264 (branch stable)
#   nv-codec-headers        n13.0.19.0 (13.1 does not build with ffmpeg 8.0.1)
#   AMF headers             v1.4.36 - the oldest ffmpeg 8.0.1 accepts, so the oldest AMD drivers work too
#
# Run it inside Ubuntu 24.04 with the source trees under /build/src (the package list is in README.md next
# to this script). The Linux binary then needs glibc 2.38 or newer and only libraries whose names have not
# changed in years (libva, libdrm, libxcb, libpulse, zlib); x264 is linked in. The Windows binary is
# static: it needs nothing but Windows itself.
#
#   ./build-ffmpeg.sh linux | win | all
set -eu
J="$(nproc)"
SRC=/build/src
FF="$SRC/ffmpeg-8.0.1"

headers() {   # $1 = prefix: nvenc and AMF are header-only, the drivers bring the libraries
  make -C "$SRC/nv-codec-headers-n13.0.19.0" PREFIX="$1" install >/dev/null
  mkdir -p "$1/include"
  rm -rf "$1/include/AMF"
  cp -r "$SRC/amf-headers-v1.4.36/AMF" "$1/include/AMF"
}

x264() {   # $1 = prefix, $2... = extra configure flags
  local prefix="$1"; shift
  rm -rf /build/b-x264 && cp -r "$SRC/x264" /build/b-x264
  (cd /build/b-x264 && ./configure --prefix="$prefix" --enable-static --disable-cli --disable-opencl "$@" >/dev/null \
     && make -j"$J" >/dev/null && make install-lib-static >/dev/null)
}

build_linux() {
  local P=/build/prefix-linux B=/build/b-linux
  headers "$P"
  x264 "$P" --enable-pic
  rm -rf "$B" && mkdir -p "$B" && cd "$B"
  PKG_CONFIG_PATH="$P/lib/pkgconfig" "$FF/configure" --prefix="$P" \
    --disable-autodetect --enable-gpl --enable-libx264 \
    --enable-ffnvcodec --enable-nvenc --enable-amf --enable-vaapi --enable-libdrm \
    --enable-libxcb --enable-libxcb-shm --enable-libxcb-xfixes --enable-libxcb-shape \
    --enable-libpulse --enable-zlib \
    --disable-doc --disable-debug --disable-ffplay --disable-ffprobe \
    --extra-cflags="-I$P/include" --extra-ldflags="-L$P/lib -static-libgcc" >"$B/configure.out"
  make -j"$J" >"$B/make.out" 2>&1
  make install >/dev/null
  mkdir -p /build/out/linux && install -m 755 "$P/bin/ffmpeg" /build/out/linux/ffmpeg
  strip --strip-all /build/out/linux/ffmpeg
}

build_win() {
  local P=/build/prefix-win B=/build/b-win
  headers "$P"
  x264 "$P" --host=x86_64-w64-mingw32 --cross-prefix=x86_64-w64-mingw32-
  rm -rf "$B" && mkdir -p "$B" && cd "$B"
  PKG_CONFIG_LIBDIR="$P/lib/pkgconfig" "$FF/configure" --prefix="$P" \
    --arch=x86_64 --target-os=mingw32 --cross-prefix=x86_64-w64-mingw32- \
    --pkg-config=pkg-config --pkg-config-flags=--static \
    --disable-autodetect --enable-gpl --enable-libx264 \
    --enable-ffnvcodec --enable-nvenc --enable-amf --enable-d3d11va --enable-dxva2 \
    --disable-doc --disable-debug --disable-ffplay --disable-ffprobe \
    --extra-cflags="-I$P/include" --extra-ldflags="-L$P/lib -static" >"$B/configure.out"
  make -j"$J" >"$B/make.out" 2>&1
  make install >/dev/null
  mkdir -p /build/out/win && install -m 755 "$P/bin/ffmpeg.exe" /build/out/win/ffmpeg.exe
  x86_64-w64-mingw32-strip --strip-all /build/out/win/ffmpeg.exe
}

case "${1:-all}" in
  linux) build_linux ;;
  win)   build_win ;;
  all)   build_linux; build_win ;;
  *)     echo "usage: $0 linux|win|all" >&2; exit 2 ;;
esac
echo "done: ${1:-all}"
