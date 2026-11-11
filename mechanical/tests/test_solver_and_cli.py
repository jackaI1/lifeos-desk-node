"""CalculiX solver checks, the closed-form cantilever benchmark, and the command line."""
import json
import math

import pytest

from enclosure_fea import __main__ as cli
from enclosure_fea.board import CaseParams
from enclosure_fea.geometry import mesh_case
from enclosure_fea.solver import parse_dat, solver_executable, von_mises
from enclosure_fea.studies import _solve, cantilever_check
from enclosure_fea.studies import MATERIALS, PRINTED


DAT_SAMPLE = """
displacements (vx,vy,vz) for set ALL and time  1.0000000E+00

     1  0.0E+00  0.0E+00  0.0E+00
     2  1.0E-01 -2.0E-01  3.0E-01

stresses (exx,eyy,ezz,exy,exz,eyz) ET,IP,mat,... for set SOLID and time  1.0000000E+00

     1   1  1.0E+00  0.0E+00  0.0E+00  0.0E+00  0.0E+00  0.0E+00
     1   2  2.0E+00  0.0E+00  0.0E+00  0.0E+00  0.0E+00  0.0E+00

forces (fx,fy,fz) for set SUPPORTS and time  1.0000000E+00

     3  0.0E+00  0.0E+00  1.0E+00
"""


def test_von_mises_uniaxial_and_pure_shear():
    assert von_mises([10.0, 0, 0, 0, 0, 0]) == pytest.approx(10.0)
    assert von_mises([0, 0, 0, 5.0, 0, 0]) == pytest.approx(math.sqrt(3) * 5.0)


def test_parse_dat_reads_each_table(tmp_path):
    path = tmp_path / 'sample.dat'
    path.write_text(DAT_SAMPLE)
    data = parse_dat(path)
    assert data['displacements'][2] == pytest.approx((0.1, -0.2, 0.3))
    assert data['stresses'][(1, 2)][0] == pytest.approx(2.0)
    assert data['forces'][3] == pytest.approx((0.0, 0.0, 1.0))


def test_parse_dat_rejects_missing_tables(tmp_path):
    path = tmp_path / 'short.dat'
    path.write_text('displacements (vx,vy,vz)\n\n     1  0.0E+00  0.0E+00  0.0E+00\n')
    with pytest.raises(ValueError):
        parse_dat(path)


def test_parse_dat_rejects_duplicate_rows(tmp_path):
    path = tmp_path / 'dup.dat'
    path.write_text(DAT_SAMPLE.replace('     2  1.0E-01', '     1  1.0E-01'))
    with pytest.raises(ValueError):
        parse_dat(path)


def test_ccx_is_found_or_fails_clearly(monkeypatch):
    monkeypatch.setenv('CCX', 'no-such-solver-binary')
    with pytest.raises(RuntimeError, match='CCX'):
        solver_executable()


def test_cantilever_matches_closed_form(tmp_path):
    result = cantilever_check(tmp_path)
    assert result['deflection_error'] < 0.01
    assert result['bending_stress_rms_error'] < 0.005
    assert result['bending_stress_max_error'] < 0.01


def test_coarse_drop_case_runs_and_reports_safety_factor(tmp_path):
    params = CaseParams().validate()
    mesh = mesh_case(params, 2.0)
    result = _solve(tmp_path, 'drop-smoke', mesh, params, MATERIALS[PRINTED], 'drop')
    assert result['peak_von_mises_mpa'] > 0
    assert result['load_point_deflection_mm'] < 0          # pushed down
    assert result['safety_factor'] == pytest.approx(
        MATERIALS[PRINTED]['yield_mpa'] / result['peak_von_mises_mpa'])
    assert abs(result['force_balance_error']) < 1e-3


def test_cli_stackup_prints_json(capsys):
    assert cli.main(['stackup']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data['vertical']['worst_case_pass'] is True


def test_cli_step_writes_file(tmp_path, capsys):
    out = tmp_path / 'case.step'
    assert cli.main(['step', '--out', str(out)]) == 0
    assert out.read_text(errors='replace').startswith('ISO-10303-21')
