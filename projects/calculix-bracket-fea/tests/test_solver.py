import pytest
from fea.solver import solver_executable


def test_explicit_ccx_override_works_without_default_on_path(monkeypatch):
    monkeypatch.setenv('PATH','')
    monkeypatch.setenv('CCX','/usr/bin/true')
    assert solver_executable() == '/usr/bin/true'


def test_invalid_explicit_override_is_not_silently_ignored(monkeypatch):
    monkeypatch.setenv('CCX','/no/such/calculix')
    with pytest.raises(RuntimeError,match='CCX'):
        solver_executable()
