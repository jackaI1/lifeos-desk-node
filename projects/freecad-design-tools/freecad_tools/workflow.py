"""Single-machine PDM-style check-in with locked, content-addressed snapshots.

This is an audit-friendly local file workflow, not authentication or multi-host PDM.
"""

import fcntl
import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class WorkflowError(ValueError):
    """A check-in, transition or integrity rule was violated."""


def _atomic_write(path, data):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Vault:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "objects").mkdir(exist_ok=True)

    @contextmanager
    def _index(self, write=False):
        with (self.root / ".lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
            path = self.root / "index.json"
            data = json.loads(path.read_text()) if path.exists() else {"version": 1, "parts": {}}
            if data.get("version") != 1 or not isinstance(data.get("parts"), dict):
                raise WorkflowError("Unsupported vault index")
            yield data
            if write:
                _atomic_write(path, (json.dumps(data, indent=2) + "\n").encode())

    @staticmethod
    def _id(part_id):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", part_id):
            raise WorkflowError(
                "Part ID must be 1-64 letters, numbers, dots, underscores or hyphens"
            )

    @staticmethod
    def _event(action):
        return {"action": action, "at": datetime.now(timezone.utc).isoformat()}

    def _object(self, record):
        return self.root / "objects" / (record["sha256"] + ".FCStd")

    def _verify(self, record):
        path = self._object(record)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise WorkflowError("Snapshot integrity check failed")

    def check_in(self, part_id, source, *, expected_version):
        self._id(part_id)
        content = Path(source).read_bytes()
        if not content:
            raise WorkflowError("Cannot check in an empty file")
        digest = hashlib.sha256(content).hexdigest()
        with self._index(write=True) as index:
            records = index["parts"].setdefault(part_id, [])
            latest = records[-1] if records else None
            revision = latest["revision"] if latest else 0
            version = latest["version"] if latest else 0
            if version != expected_version:
                raise WorkflowError("Stale version; reload history before check-in")
            if latest and latest["state"] == "review":
                raise WorkflowError("Return review to draft before changing its contents")
            if latest and latest["state"] == "released":
                self._verify(latest)
            if not latest or latest["state"] == "released":
                latest = {"revision": revision + 1, "state": "draft", "events": []}
                records.append(latest)
            latest.update(sha256=digest, source_name=Path(source).name, version=version + 1)
            destination = self._object(latest)
            if destination.exists():
                self._verify(latest)
            else:
                _atomic_write(destination, content)
            latest["events"].append({**self._event("check-in"), "sha256": digest})
            return dict(latest)

    def transition(self, part_id, state, *, expected_version):
        self._id(part_id)
        allowed = {"draft": {"review"}, "review": {"draft", "released"}, "released": set()}
        with self._index(write=True) as index:
            records = index["parts"].get(part_id, [])
            if not records or records[-1]["version"] != expected_version:
                raise WorkflowError("Unknown part or stale version")
            record = records[-1]
            if state not in allowed[record["state"]]:
                raise WorkflowError(f"Invalid transition: {record['state']} -> {state}")
            self._verify(record)
            record["state"] = state
            record["version"] += 1
            record["events"].append(self._event(state))
            return dict(record)

    def history(self, part_id):
        self._id(part_id)
        with self._index() as index:
            return index["parts"].get(part_id, [])

    def snapshot(self, part_id, revision):
        for record in self.history(part_id):
            if record["revision"] == revision:
                self._verify(record)
                return self._object(record)
        raise WorkflowError("Unknown revision")
