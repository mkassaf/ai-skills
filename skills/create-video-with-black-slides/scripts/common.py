"""Shared executable discovery for the black lightboard helpers."""
import os
import shutil
from pathlib import Path


def ffmpeg_binary(explicit=None):
    candidates = [explicit, os.environ.get('FFMPEG'), shutil.which('ffmpeg'),
                  '/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg',
                  '/Applications/Weline Pro.app/Contents/Resources/mac_pc_nas/ffmpeg']
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise RuntimeError('FFmpeg is required. Set FFMPEG=/absolute/path/to/ffmpeg or put it on PATH.')
