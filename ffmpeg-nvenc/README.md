# Patched ffmpeg (optional)

Stock ffmpeg works with the server. These two patches unlock three extra switches that make the
stream cheaper for the PS3 to decode; the server finds them by itself (`ffmpeg -h encoder=...`) and
only then shows the options.

| Patch | Adds | Server option |
|---|---|---|
| `nvenc-dblk_idc-mv_precision.patch` | `h264_nvenc -dblk_idc`, `-mv_precision` | NVENC deblocking filter **Off**, motion vectors **Whole pixels** |
| `mpeg2-intra-refresh.patch` | `mpeg2video -intra_refresh <frames>` | MPEG-2 test codec heals with an intra-refresh sweep instead of keyframes |

Built and tested against **ffmpeg 8.0.1** with **nv-codec-headers n13.0.19.0** (13.1 does not build
with 8.0.1).

```sh
cd ffmpeg-8.0.1
patch -p1 < nvenc-dblk_idc-mv_precision.patch
patch -p1 < mpeg2-intra-refresh.patch
./configure --enable-nonfree --enable-nvenc ... && make
```

Point the server at the result with `"ffmpeg_path": "/path/to/ffmpeg"` in `~/.config/tee-cell-stream-server/settings.json`, or put it first in `PATH`.
