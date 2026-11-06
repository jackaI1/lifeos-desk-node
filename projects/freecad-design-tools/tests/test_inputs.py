import pytest

from freecad_tools.workflow import Vault, WorkflowError


def test_empty_checkin_cannot_create_a_revision(tmp_path):
    source = tmp_path / "empty.FCStd"
    source.touch()
    vault = Vault(tmp_path / "vault")
    with pytest.raises(WorkflowError, match="empty"):
        vault.check_in("PL", source, expected_version=0)
    assert vault.history("PL") == []


def test_release_keeps_checked_in_snapshot_when_working_file_changes(tmp_path):
    source = tmp_path / "working.FCStd"
    source.write_bytes(b"reviewed bytes")
    vault = Vault(tmp_path / "vault")
    vault.check_in("PL", source, expected_version=0)
    vault.transition("PL", "review", expected_version=1)
    source.write_bytes(b"unreviewed working edit")
    vault.transition("PL", "released", expected_version=2)
    assert vault.snapshot("PL", 1).read_bytes() == b"reviewed bytes"
