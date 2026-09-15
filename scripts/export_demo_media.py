"""Export reviewed App recordings using the cuts in a capture manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
from importlib import import_module
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    imageio_ffmpeg = import_module("imageio_ffmpeg")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    font = str(args.font.resolve())
    if any(char in font for char in "':,;[]"):
        raise SystemExit("Use a font path without FFmpeg filter separators.")
    for clip in manifest["clips"]:
        filters = []
        for index, (start, end) in enumerate(clip["segments"]):
            redact = ""
            if clip["file"] == "cleanup.gif" and index < 3:
                redact = (
                    ",drawbox=x=430:y=169:w=616:h=44:color=0x252525:t=fill"
                    f",drawtext=fontfile='{font}':text='Local storage path redacted'"
                    ":x=445:y=181:fontsize=16:fontcolor=white"
                )
            filters.append(f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS{redact}[v{index}]")
        count = len(clip["segments"])
        caption = clip["caption"]
        if any(char in caption for char in "':;[]"):
            raise SystemExit("Use a caption without FFmpeg filter separators.")
        filters.append(
            "".join(f"[v{index}]" for index in range(count)) + f"concat=n={count}:v=1:a=0,crop=784:952:328:24,fps=8,"
            "pad=784:994:0:42:color=0x181818,"
            f"drawtext=fontfile='{font}':text='{caption}':x=18:y=12:fontsize=18:fontcolor=0xffb36b,"
            "split[s0][s1];[s0]palettegen=max_colors=160:stats_mode=diff[p];"
            "[s1][p]paletteuse=dither=bayer:bayer_scale=3"
        )
        name = clip["file"]
        if Path(name).name != name or not name.endswith(".gif"):
            raise SystemExit("Each clip must name a GIF in the output directory.")
        output = args.output_dir / name
        subprocess.run(  # noqa: S603
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(args.source),
                "-filter_complex",
                ";".join(filters),
                "-loop",
                "0",
                str(output),
            ],
            check=True,
        )
        if output.stat().st_size > 5 * 1024 * 1024:
            raise SystemExit(f"Optimize {name}: the export exceeds 5 MiB.")
        print(f"{name}: {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
