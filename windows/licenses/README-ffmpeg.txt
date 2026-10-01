ffmpeg.exe - wie es gebaut wurde  /  how this ffmpeg.exe was built
===================================================================

Version:      ffmpeg 8.0.1 mit zwei Patches von TEE PS3 Remoteplay (64-bit, statisch, Windows)
              ffmpeg 8.0.1 with two patches by TEE PS3 Remoteplay (64-bit, static, Windows)

Bestandteile / components:
  ffmpeg 8.0.1           https://ffmpeg.org/releases/ffmpeg-8.0.1.tar.xz
                         (signiert mit dem FFmpeg-Release-Schluessel / signed with the FFmpeg release key
                          FCF986EA15E6E293A5644F10B4322F04D67658D8)
  Patches                nvenc-dblk_idc-mv_precision.patch   h264_nvenc -dblk_idc und -mv_precision
                         mpeg2-intra-refresh.patch           mpeg2video -intra_refresh
  x264 r3222 b35605a     https://code.videolan.org/videolan/x264 (Zweig / branch stable)
  nv-codec-headers       n13.0.19.0 (nur Header / headers only)
  AMF-Header             v1.4.36 (nur Header / headers only)

Gebaut mit build-ffmpeg.sh unter Ubuntu 24.04 mit mingw-w64 (GCC 13).
Built with build-ffmpeg.sh on Ubuntu 24.04 with mingw-w64 (GCC 13).

  configuration:
    --prefix=/build/prefix-win
    --arch=x86_64
    --target-os=mingw32
    --cross-prefix=x86_64-w64-mingw32-
    --pkg-config=pkg-config --pkg-config-flags=--static
    --disable-autodetect
    --enable-gpl
    --enable-libx264
    --enable-ffnvcodec
    --enable-nvenc
    --enable-amf
    --enable-d3d11va
    --enable-dxva2
    --disable-doc
    --disable-debug
    --disable-ffplay
    --disable-ffprobe
    --extra-cflags=-I/build/prefix-win/include
    --extra-ldflags='-L/build/prefix-win/lib -static'

Lizenz / licence: GNU General Public License Version 2 oder spaeter / version 2 or later
                  (LICENSE-ffmpeg.txt). Quelltext / source: QUELLE-ffmpeg.txt
