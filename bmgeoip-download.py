#!/usr/bin/env python3
"""Run the enabled CSV download schedule from cron."""

import logging
import argparse
from pathlib import Path

from bmgeoip.interface.DownloadRunner import run


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    raise SystemExit(0 if run(args.state_dir) else 1)
