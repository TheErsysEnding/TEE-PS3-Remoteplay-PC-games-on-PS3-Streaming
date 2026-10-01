# The patched ffmpeg

Since 1.1.1 the Linux package brings this ffmpeg along, and so does the Windows installer from its 1.1.1
release on, so nothing here has to be done by hand: the Linux package puts it at
`/usr/lib/tee-cell-stream-server/ffmpeg/ffmpeg`, the Windows installer next to the server's `.exe`. The
server finds the extra options by itself (`ffmpeg -h encoder=...`) and only then offers them in the window. A stock ffmpeg still works - the three switches are then simply absent.

| Patch | Adds | Server option |
|---|---|---|
| `nvenc-dblk_idc-mv_precision.patch` | `h264_nvenc -dblk_idc`, `-mv_precision` | NVENC deblocking filter **Off**, motion vectors **Whole pixels** |
| `mpeg2-intra-refresh.patch` | `mpeg2video -intra_refresh <frames>` | the MPEG-2 test codec heals with an intra-refresh sweep instead of keyframes |

## What exactly is shipped

`build-ffmpeg.sh` is the whole recipe. It builds, inside Ubuntu 24.04:

- **ffmpeg 8.0.1** (`ffmpeg-8.0.1.tar.xz`, signed with the FFmpeg release key
  `FCF986EA15E6E293A5644F10B4322F04D67658D8`) with the two patches above
- **x264 r3222 b35605a** (branch `stable`), linked in
- **nv-codec-headers n13.0.19.0** (13.1 does not build with 8.0.1) and **AMF headers v1.4.36** - the
  oldest ffmpeg 8.0.1 accepts, so that the oldest possible AMD drivers still run it

for **Linux** (x86_64, needs glibc 2.38 - Ubuntu 24.04, Debian 13 and newer - and only libva, libdrm,
libxcb, libpulse and zlib from the system) and for **Windows** (x86_64, fully static: nothing but Windows
itself). `--enable-gpl` without `--enable-nonfree`, so both binaries may be redistributed under the
GPL v2 or later.

The complete corresponding source - the ffmpeg tarball, the patches, x264, both header packages and the
script - is attached to every release as `tee-ps3-remoteplay-ffmpeg-source-<version>.tar.xz`.

## Building it yourself

In Ubuntu 24.04 with `build-essential nasm pkgconf libva-dev libdrm-dev libxcb1-dev libxcb-shm0-dev
libxcb-shape0-dev libxcb-xfixes0-dev libpulse-dev zlib1g-dev` (and for Windows
`gcc-mingw-w64-x86-64-win32 g++-mingw-w64-x86-64-win32 binutils-mingw-w64-x86-64 mingw-w64-x86-64-dev`),
with the source trees unpacked under `/build/src` and the patches applied to ffmpeg:

```sh
./build-ffmpeg.sh linux   # -> /build/out/linux/ffmpeg
./build-ffmpeg.sh win     # -> /build/out/win/ffmpeg.exe
```

To use another build with the server, set `"ffmpeg_path": "/path/to/ffmpeg"` in
`~/.config/tee-cell-stream-server/settings.json` (Windows: `%APPDATA%\TEE PS3 Remoteplay\settings.json`).
