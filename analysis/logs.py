"""Bounded CSV import and read-only import from the existing adapter database."""
from contextlib import closing
import csv
from pathlib import Path
import sqlite3

import numpy as np

from .core import MAX_SAMPLES, Samples, validate

CHANNELS = {'temperature': ('temperature_mc', 'C'), 'humidity': ('humidity_mpermil', '%RH')}


def _samples(rows, channel):
    field, unit = CHANNELS[channel]
    times, values, truth = [], [], []
    try:
        for row in rows:
            if len(times) >= MAX_SAMPLES:
                raise ValueError('log exceeds 200000 samples; select a shorter interval')
            times.append(float(row['timestamp']))
            values.append(float(row[field])/1000)
            if 'true_' + field in row:
                truth.append(float(row['true_' + field])/1000)
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError(f'expected timestamp and {field}, with numeric values') from exc
    data = Samples(np.array(times), np.array(values), np.array(truth) if truth else None, unit)
    validate(data.times, data.values, data.truth)
    return data


def load_csv(path, channel='temperature'):
    path = Path(path)
    if path.stat().st_size > 32_000_000:
        raise ValueError('CSV exceeds 32 MB; crop the log first')
    try:
        with path.open(newline='') as stream:
            return _samples(csv.DictReader(stream), channel)
    except csv.Error as exc:
        raise ValueError('malformed CSV or field exceeds 128 KiB') from exc


def load_database(path, device, channel='temperature', start=None, end=None):
    """Select one device and optional inclusive epoch interval. No schema changes."""
    if start is not None and end is not None and start > end:
        raise ValueError('start must be <= end')
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    field, _ = CHANNELS[channel]
    query = f'SELECT timestamp, {field} FROM readings WHERE device=?'
    params = [device]
    if start is not None:
        query += ' AND timestamp>=?'
        params.append(start)
    if end is not None:
        query += ' AND timestamp<=?'
        params.append(end)
    query += ' ORDER BY timestamp LIMIT ?'
    params.append(MAX_SAMPLES+1)
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=1)) as db:
            db.row_factory = sqlite3.Row
            return _samples((dict(row) for row in db.execute(query, params)), channel)
    except sqlite3.Error as exc:
        raise ValueError('cannot read adapter database; check path, readings schema and device') from exc
