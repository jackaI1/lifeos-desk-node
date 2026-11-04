from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from automation.sources import AdapterSource


# Use the real adapter's schema, validation and ingestion, not a second schema.
spec = importlib.util.spec_from_file_location('desk_api', Path(__file__).parents[2] / 'firmware/tools/desk_api.py')
desk_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desk_api)


def batch(timestamp=1000, temp=20000, device='abcdef123456', sequence=1):
    return {'device': device, 'session': '0123456789abcdef', 'dropped': 0,
            'readings': [{'sequence': sequence, 'timestamp': timestamp,
                          'temperature_mc': temp, 'humidity_mpermil': 45250}]}


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'room.sqlite3'
        self.source = AdapterSource(self.path, 'abcdef123456')

    def adapter(self):
        adapter = desk_api.Gateway(self.path, desk_api.DemoLifeOS(),
            now=lambda: datetime.fromtimestamp(3000, timezone.utc))
        self.addCleanup(adapter.close)
        return adapter

    def test_missing_database_not_created(self):
        self.assertIsNone(self.source.sample(1000, False))
        self.assertFalse(self.path.exists())

    def test_existing_ingestion_and_device_filter(self):
        adapter = self.adapter()
        adapter.ingest(batch())
        adapter.ingest(batch(timestamp=1100, temp=27000, device='000000000000'))
        reading = self.source.sample(1100, False)
        self.assertEqual((reading.temperature, reading.humidity, reading.timestamp), (20, 45.25, 1000))

    def test_backlog_upload_does_not_replace_newest_measurement(self):
        adapter = self.adapter()
        adapter.ingest(batch(timestamp=2000, temp=23000))
        adapter.ingest(batch(timestamp=1500, temp=18000, sequence=2))
        adapter.ingest(batch(timestamp=0, temp=19000, sequence=3))
        self.assertEqual(self.source.sample(2100, False).temperature, 23)

    def test_unknown_time_is_not_current(self):
        self.adapter().ingest(batch(timestamp=0))
        self.assertIsNone(self.source.sample(3000, False))

    def test_new_commits_visible_and_database_read_only(self):
        adapter = self.adapter()
        adapter.ingest(batch())
        self.assertEqual(self.source.sample(2000, False).temperature, 20)
        adapter.ingest(batch(timestamp=2000, temp=24000, sequence=2))
        self.assertEqual(self.source.sample(2000, False).temperature, 24)
        with closing(sqlite3.connect(self.source.uri, uri=True)) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM readings')

    def test_corrupt_database_is_missing_input(self):
        self.path.write_text('invalid SQLite')
        self.assertIsNone(self.source.sample(1000, False))
