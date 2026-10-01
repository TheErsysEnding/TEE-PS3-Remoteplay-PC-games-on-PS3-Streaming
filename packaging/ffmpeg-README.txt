The ffmpeg bundled with TEE Cell Stream Server
==============================================

/usr/lib/tee-cell-stream-server/ffmpeg/ffmpeg is used only by this program. It is not on PATH and does
not replace your distribution's ffmpeg; if it cannot run, the server uses the distribution's instead.

What it is
  ffmpeg 8.0.1 (https://ffmpeg.org/releases/ffmpeg-8.0.1.tar.xz, signed with the FFmpeg release key
  FCF986EA15E6E293A5644F10B4322F04D67658D8) with the patches in this folder:
    nvenc-dblk_idc-mv_precision.patch   h264_nvenc -dblk_idc and -mv_precision
    mpeg2-intra-refresh.patch           mpeg2video -intra_refresh
  linked with x264 r3222 b35605a (https://code.videolan.org/videolan/x264, branch stable),
  nv-codec-headers n13.0.19.0 and AMF headers v1.4.36.
  Built by build-ffmpeg.sh (in this folder) inside Ubuntu 24.04.

Licence
  GNU General Public License, version 2 or later (ffmpeg configured with --enable-gpl, x264 is GPL-2+).
  Full text: /usr/share/common-licenses/GPL-2

Source
  The complete corresponding source - the ffmpeg tarball, the patches, x264, the two header packages
  and the build script - is attached to every release as
  tee-ps3-remoteplay-ffmpeg-source-<version>.tar.xz:
    https://github.com/TheErsysEnding/TEE-PS3-Remoteplay-PC-games-on-PS3-Streaming/releases
