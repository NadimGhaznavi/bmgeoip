#!/usr/bin/env python3
"""Run the enabled CSV download schedule from cron."""

import logging
import argparse
from pathlib import Path

from bmgeoip.interface.DownloadRunner import run
from bmgeoip.constants.DGeoIp import DGeoIp


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--database-env', type=Path, default=Path(DGeoIp.DATABASE_ENV))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    raise SystemExit(0 if run(args.state_dir, args.database_env) else 1)
