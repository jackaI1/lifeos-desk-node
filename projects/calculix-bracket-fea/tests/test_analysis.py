import math
import pytest
from fea.analysis import cantilever, von_mises, parse_dat


def test_beam_hand_calculation_and_load_scaling():
    # 100 mm long, 10 x 5 mm, 10 N, E=70000 N/mm²:
    # I=104.1666667 mm^4, PL^3/(3EI)=0.457142857 mm, PLc/I=24 MPa.
    d, s = cantilever(100, 10, 5, 10, 70000)
    assert d == pytest.approx(0.45714285714285713)
    assert s == pytest.approx(24.0)
    assert cantilever(100, 10, 5, 20, 70000) == pytest.approx((2*d, 2*s))


@pytest.mark.parametrize('args', [(0,10,5,10,70000), (100,-10,5,10,70000),
                                  (100,10,5,10,0), (100,10,5,math.nan,70000)])
def test_invalid_hand_calculation(args):
    with pytest.raises(ValueError):
        cantilever(*args)


@pytest.mark.parametrize('stress,want', [((100,0,0,0,0,0),100),
    ((20,20,20,0,0,0),0), ((0,0,0,10,0,0),math.sqrt(300))])
def test_von_mises_known_states(stress, want):
    assert von_mises(stress) == pytest.approx(want)


def test_parser_maps_noncontiguous_ids_and_fortran_exponents(tmp_path):
    p = tmp_path/'case.dat'
    p.write_text(''' displacements (vx,vy,vz) for set ALL and time  1.000E+00

 7 1.0D-03 -2.0E-03 3.0E-03
 42 0 0 -4.0E-03

 stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set SOLID and time 1

 9 1 100 0 0 0 0 0
 9 2 0 0 0 10 0 0

 forces (fx,fy,fz) for set FIXED and time 1

 7 0 0 10
''')
    r = parse_dat(p)
    assert r['displacements'][42] == (0,0,-0.004)
    assert r['stresses'][(9,2)] == (0,0,0,10,0,0)
    assert r['forces'][7] == (0,0,10)


@pytest.mark.parametrize('content', ['', ' displacements for set ALL\n\n1 0 nan 0\n',
    ' displacements for set ALL\n\n1 0 0\n'])
def test_parser_rejects_empty_truncated_or_nonfinite(tmp_path, content):
    p = tmp_path/'bad.dat'
    p.write_text(content)
    with pytest.raises(ValueError):
        parse_dat(p)
