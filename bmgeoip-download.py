#!/usr/bin/env python3
"""Run the enabled CSV download schedule from cron."""

import logging

from bmgeoip.interface.DownloadRunner import run


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    raise SystemExit(0 if run() else 1)
