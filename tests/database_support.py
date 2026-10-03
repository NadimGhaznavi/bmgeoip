"""Opt-in MariaDB integration fixtures, isolated from application databases."""

import os
from pathlib import Path
from uuid import uuid4

import pymysql

from bmgeoip.interface.DatabaseEnvironment import DatabaseEnvironment


def database_settings(test, path):
    source = os.environ.get('BMGEOIP_TEST_DATABASE_ENV')
    if not source:
        test.skipTest('Set BMGEOIP_TEST_DATABASE_ENV for isolated MariaDB integration checks.')
    values = DatabaseEnvironment.read(Path(source))
    admin = pymysql.connect(host=values['DB_HOST'], port=int(values['DB_PORT']),
                            user=values['DB_USER'], password=values['DB_PASSWORD'],
                            unix_socket=values.get('DB_SOCKET'), autocommit=True)
    name = 'bmgeoip_test_' + uuid4().hex
    try:
        with admin.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
    except BaseException:
        admin.close()
        raise

    def cleanup():
        try:
            with admin.cursor() as cursor:
                cursor.execute(f'DROP DATABASE `{name}`')
        finally:
            admin.close()

    test.addCleanup(cleanup)
    values['DB_NAME'] = name
    path.write_text(''.join(f'{key}={value}\n' for key, value in values.items()))
    path.chmod(0o600)
    return path
