"""Generate a small synthetic video library + database so the app can be tried
instantly, without any personal media.

Requires the ffmpeg binary. Uses ffmpeg lavfi test sources (color patterns,
gradients) as stand-in "clips", then scans them through the normal pipeline
(scanner -> parquet db), exactly like a real rescan would.

Refuses to overwrite an existing database unless FORCE=1 is set.

Usage:
    make demo                                          # isolated playground + UI
    LIBRARY_DIR=... LIBRARY_DB=... uv run python scripts/make_demo_data.py
    COUNT=30 ...                                       # more clips
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from library_of_mess import config, database
from library_of_mess.scanner import find_videos, parse_video_paths

# visually distinct lavfi sources, cycled through
SCENES = ["testsrc2", "smptebars", "mandelbrot", "gradients", "cellauto", "life"]

DURATION = 3  # seconds per clip
SIZE = "320x180"
RATE = 10


def make_clip(out_path: Path, scene: str, index: int) -> None:
    """One tiny mp4 from an lavfi source; filename hints at fake content."""
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            f"{scene}=size={SIZE}:rate={RATE}",
            # -t works for every lavfi source; several of them (mandelbrot,
            # cellauto, life) have no native duration option
            "-t",
            str(DURATION),
            "-y",
            "-loglevel",
            "error",
            str(out_path),
        ],
        check=True,
    )
    print(f"  {out_path.name}  ({scene}, #{index})")


def main() -> int:
    db_file = config.db_path()
    if db_file.exists() and os.environ.get("FORCE") != "1":
        print(
            f"error: refusing to overwrite existing database {db_file}\n"
            "Set FORCE=1 to overwrite, or use 'make demo' which runs isolated "
            "under .cache/demo/.",
            file=sys.stderr,
        )
        return 1

    if shutil.which("ffmpeg") is None:
        print("error: ffmpeg binary not found on PATH", file=sys.stderr)
        return 1

    library = config.library_dir()
    library.mkdir(parents=True, exist_ok=True)
    count = int(os.environ.get("COUNT", "12"))

    print(f"Generating {count} demo clips in {library} ...")
    existing = len(find_videos(library))
    for i in range(existing, existing + count):
        scene = SCENES[i % len(SCENES)]
        name = f"demo_ride_{i:03d}_{scene}.mp4"
        make_clip(library / name, scene, i)

    print("Scanning into database ...")
    df = parse_video_paths(find_videos(library))
    database.save_db(df, db_file)
    print(f"Done: {len(df)} entries in {db_file}")
    print("Run 'make demo' and open http://localhost:8501")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
