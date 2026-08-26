import shutil
from pathlib import Path

import pytest

from library_of_mess.thumbnails import (
    generate_search_frames,
    generate_thumbnail_from_video,
    generate_thumbnails,
)

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


def test_generate_search_frames_samples_at_interval(tmp_path: Path, tiny_video: Path) -> None:
    frames_dir = tmp_path / "_search"
    frames = generate_search_frames(tiny_video, frames_dir=frames_dir, timestamps=[0.0, 0.4, 0.8])

    assert len(frames) >= 2
    assert all(p.parent == frames_dir for p in frames)
    names = [f.name for f in frames]
    stem = tiny_video.stem
    assert all(n.startswith(f"{stem}.f") and n.endswith(".jpg") for n in names)
    # resume-safe: rerun into the same frames_dir keeps existing files
    again = generate_search_frames(tiny_video, frames_dir=frames_dir, timestamps=[0.0, 0.4, 0.8])
    assert {f.name for f in again} == set(names)


def test_generate_search_frames_reports_ffmpeg_stderr(
    tmp_path: Path, tiny_video: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: failures must surface the real ffmpeg stderr, not a generic message."""
    import ffmpeg as ffmpeg_lib

    from library_of_mess import thumbnails

    class FakeChain:
        def filter(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return self

        def output(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return self

        def run(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise ffmpeg_lib.Error("ffmpeg", b"", b"decode\ncorrupt data at frame 12\n")

    monkeypatch.setattr(thumbnails.ffmpeg, "input", lambda *args, **kwargs: FakeChain())
    with pytest.raises(ffmpeg_lib.Error), caplog.at_level("WARNING"):
        generate_search_frames(tiny_video, frames_dir=tmp_path, timestamps=[0.0, 0.2])

    assert "corrupt data at frame 12" in caplog.text


def test_generate_search_frames_skips_unseekable_timestamps(tmp_path: Path, tiny_video: Path) -> None:
    """Regression: a seek past the last frame (1s clip, t=0.8 requested) must
    skip that timestamp — not abort the batch or wipe extracted siblings."""
    frames = generate_search_frames(tiny_video, frames_dir=tmp_path / "_search", timestamps=[0.0, 0.4, 0.8])

    names = [f.name for f in frames]
    assert "tiny.f0000.jpg" in names and "tiny.f0001.jpg" in names
    assert all(p.exists() for p in frames)
