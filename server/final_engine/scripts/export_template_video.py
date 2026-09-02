"""Shared export profile used by the finished-video job preparer."""

PROFILE = {
    "canvas": {"width": 1080, "height": 2400},
    "fps": 30,
    "codec": "h264",
    "format": "mp4",
    "duration_tolerance_seconds": 1.0,
    "audio": "allow",
}
