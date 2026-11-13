"""CLI compatibility entry for the V3 composition diagnostic reporter."""
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.ffmpeg_finals.diagnostic_report import (
    LABELS, analyze, export_bundle, load_operations, load_records, main, measures, profile,
)

if __name__ == '__main__':
    main()
