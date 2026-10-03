"""Refresh and import both CSV families without overlapping another worker."""

from bmgeoip.activity.DataLoader import DataLoader
from bmgeoip.interface.DownloadSchedule import DownloadSchedule
from pathlib import Path


def run(state_dir: Path | None = None) -> bool:
    if state_dir is None:
        loader = DataLoader()
    else:
        loader = DataLoader(
            DownloadSchedule(state_dir / 'download-schedule.json', state_dir / 'data'),
            state_dir / 'geoip.sqlite3', state_dir / 'data-status.json')
    return loader.run(refresh=True)
