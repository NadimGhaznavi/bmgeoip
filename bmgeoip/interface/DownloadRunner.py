"""Refresh and import both CSV families without overlapping another worker."""

from bmgeoip.activity.DataLoader import DataLoader
from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.DownloadSchedule import DownloadSchedule
from pathlib import Path


def run(state_dir: Path | None = None, database: Path = Path(DGeoIp.DATABASE_ENV)) -> bool:
    if state_dir is None:
        loader = DataLoader(database=database)
    else:
        loader = DataLoader(
            DownloadSchedule(state_dir / 'download-schedule.json', state_dir / 'data'),
            database, state_dir / 'data-status.json')
    return loader.run(refresh=True)
