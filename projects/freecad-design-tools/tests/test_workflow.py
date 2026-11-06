import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from freecad_tools.workflow import Vault, WorkflowError


def test_release_pins_bytes_and_next_revision_preserves_history(tmp_path):
    source = tmp_path / "plate.FCStd"
    source.write_bytes(b"first design")
    vault = Vault(tmp_path / "vault")
    assert vault.check_in("PL-01", source, expected_version=0)["revision"] == 1
    vault.transition("PL-01", "review", expected_version=1)
    vault.transition("PL-01", "released", expected_version=2)
    source.write_bytes(b"second design")
    assert vault.check_in("PL-01", source, expected_version=3)["revision"] == 2
    history = vault.history("PL-01")
    assert [r["state"] for r in history] == ["released", "draft"]
    assert vault.snapshot("PL-01", 1).read_bytes() == b"first design"
    assert vault.snapshot("PL-01", 2).read_bytes() == b"second design"


def test_review_rejects_checkin_and_snapshot_tampering(tmp_path):
    source = tmp_path / "part.FCStd"
    source.write_bytes(b"design")
    vault = Vault(tmp_path / "vault")
    vault.check_in("A", source, expected_version=0)
    vault.transition("A", "review", expected_version=1)
    with pytest.raises(WorkflowError):
        vault.check_in("A", source, expected_version=2)
    vault.snapshot("A", 1).write_bytes(b"modified")
    with pytest.raises(WorkflowError, match="integrity"):
        vault.transition("A", "released", expected_version=2)
    assert vault.history("A")[0]["state"] == "review"


def test_rejected_review_can_be_edited_but_release_cannot_go_back(tmp_path):
    source = tmp_path / "part.FCStd"
    source.write_bytes(b"design")
    vault = Vault(tmp_path / "vault")
    vault.check_in("A", source, expected_version=0)
    with pytest.raises(WorkflowError):
        vault.transition("A", "released", expected_version=1)
    vault.transition("A", "review", expected_version=1)
    vault.transition("A", "draft", expected_version=2)
    source.write_bytes(b"fix")
    vault.check_in("A", source, expected_version=3)
    vault.transition("A", "review", expected_version=4)
    vault.transition("A", "released", expected_version=5)
    with pytest.raises(WorkflowError):
        vault.transition("A", "draft", expected_version=6)
    assert len(vault.history("A")[0]["events"]) == 6


@pytest.mark.parametrize("part_id", ["../escape", "", "/tmp/a", "a/b", "=SUM(A1)"])
def test_unsafe_part_ids_rejected(tmp_path, part_id):
    source = tmp_path / "part.FCStd"
    source.touch()
    with pytest.raises(WorkflowError):
        Vault(tmp_path / "vault").check_in(part_id, source, expected_version=0)


def test_stale_revision_and_concurrent_checkin_are_rejected(tmp_path):
    source = tmp_path / "part.FCStd"
    source.write_bytes(b"design")
    vault = Vault(tmp_path / "vault")

    def checkin(_):
        try:
            vault.check_in("A", source, expected_version=0)
            return True
        except WorkflowError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(checkin, range(2))) == [False, True]
    assert json.loads((tmp_path / "vault/index.json").read_text())["parts"]["A"][0]["revision"] == 1


def test_stale_draft_edit_and_transition_cannot_replace_newer_checkin(tmp_path):
    source = tmp_path / "part.FCStd"
    source.write_bytes(b"original")
    vault = Vault(tmp_path / "vault")
    first = vault.check_in("A", source, expected_version=0)
    assert first["revision"] == first["version"] == 1
    source.write_bytes(b"newer edit")
    second = vault.check_in("A", source, expected_version=1)
    assert second["revision"] == 1 and second["version"] == 2
    with pytest.raises(WorkflowError, match="Stale"):
        vault.check_in("A", source, expected_version=1)
    with pytest.raises(WorkflowError, match="stale"):
        vault.transition("A", "review", expected_version=1)
    assert vault.snapshot("A", 1).read_bytes() == b"newer edit"
