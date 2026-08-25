import shutil
from pathlib import Path

import pytest

from library_of_mess.thumbnails import generate_thumbnail_from_video, generate_thumbnails

NO_FFMPEG = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")


@NO_FFMPEG
def test_thumbnail_generated_and_cached(tmp_path: Path, tiny_video: Path) -> None:
    out_dir = tmp_path / "thumbs"

    result = generate_thumbnail_from_video(tiny_video, out_dir)

    thumb = Path(result["thumbnail"])
    assert thumb.exists()
    assert thumb.stat().st_size > 0

    mtime = thumb.stat().st_mtime
    generate_thumbnail_from_video(tiny_video, out_dir)
    assert thumb.stat().st_mtime == mtime


@NO_FFMPEG
def test_generate_thumbnails_batch(tmp_path: Path, tiny_video: Path) -> None:
    df, skipped = generate_thumbnails([str(tiny_video)], output_dir=tmp_path / "thumbs")
    assert len(df) == 1
    assert skipped == 0
    assert Path(df.iloc[0]["path"]) == tiny_video


def test_generate_thumbnails_skips_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ffmpeg as ffmpeg_lib

    import library_of_mess.thumbnails as thumbs

    good = tmp_path / "good.mp4"
    bad = tmp_path / "bad.mp4"
    good.write_bytes(b"\x00")
    bad.write_bytes(b"\x00")

    def fake(video_path: Path, output_dir: Path) -> dict:
        if video_path.name == "bad.mp4":
            raise ffmpeg_lib.Error("ffmpeg", b"", b"mock decode failure")
        return {"path": video_path, "thumbnail": output_dir / f"{video_path.stem}.jpg"}

    monkeypatch.setattr(thumbs, "generate_thumbnail_from_video", fake)

    df, skipped = thumbs.generate_thumbnails([str(good), str(bad)], output_dir=tmp_path / "thumbs")

    assert len(df) == 1
    assert skipped == 1
    assert Path(df.iloc[0]["path"]) == good


def test_missing_file_skipped_without_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ffmpeg as ffmpeg_lib

    import library_of_mess.thumbnails as thumbs

    ghost = tmp_path / "ghost.mp4"  # never created

    def fake(video_path: Path, output_dir: Path) -> dict:
        raise FileNotFoundError(video_path)

    monkeypatch.setattr(thumbs, "generate_thumbnail_from_video", fake)
    monkeypatch.setattr(ffmpeg_lib, "Error", ffmpeg_lib.Error)

    out_dir = tmp_path / "thumbs"
    df, skipped = thumbs.generate_thumbnails([str(ghost)], output_dir=out_dir)

    assert len(df) == 0 and skipped == 1
    assert not (out_dir / "ghost.jpg.fail").exists()


def test_clear_failure_markers(tmp_path: Path) -> None:
    import library_of_mess.thumbnails as thumbs

    out_dir = tmp_path / "thumbs"
    out_dir.mkdir()
    (out_dir / "a.jpg.fail").write_text("")
    (out_dir / "b.jpg.fail").write_text("")
    (out_dir / "keep.jpg").write_bytes(b"x")

    removed = thumbs.clear_failure_markers(output_dir=out_dir)

    assert removed == 2
    assert list(out_dir.iterdir())[0].name == "keep.jpg"
