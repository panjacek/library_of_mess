from pathlib import Path

import ffmpeg
from streamlit.logger import get_logger

logger = get_logger(__name__)


def generate_thumbnail(in_filename, out_filename, time, width):
    """Extract first frame of video and save it to temporary folder

    Args:
        in_filename (str): Path to video file
        out_filename (str): Path to output directory
        time (int): Time in seconds
        width (int): Width of thumbnail

    Returns:
        None

    """
    try:
        (
            ffmpeg.input(in_filename, ss=time)
            .filter("scale", width, -1)
            .output(out_filename, vframes=1)
            # .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as ffmpeg_err:
        logger.critical(e.stderr.decode())
        raise ffmpeg_err


def generate_thumbnail_from_video(video_path: Path, output_dir: Path) -> Path:
    """Extract first frame of video and save it to library folder

    Args:
        video_path (Path): Path to video file
        output_dir (Path): Path to output directory

    Returns:
        Path: Path to thumbnail generated
    """

    if not output_dir.exists():
        logger.warning(f"Creating output directory {output_dir}")
        output_dir.mkdir()

    thumbnail_path = Path.joinpath(output_dir, video_path.stem + ".jpg")
    # check if exists?
    if thumbnail_path.exists():
        logger.info(f"Thumbnail {thumbnail_path} already exists")
    else:
        logger.info(f"Extracting first frame of {video_path} to {thumbnail_path}")
        generate_thumbnail(str(video_path), str(thumbnail_path), 0, 400)

    return {"path": video_path, "thumbnail": thumbnail_path}
