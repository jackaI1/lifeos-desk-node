import pytest
from fea.analysis import parse_frd


def test_frd_fixed_width_adjacent_negatives_and_tensor_order(tmp_path):
    p = tmp_path/'case.frd'
    p.write_text(''' -4  STRESS      6    1
 -5  SXX         1    4    1    1
 -5  SYY         1    4    2    2
 -5  SZZ         1    4    3    3
 -5  SXY         1    4    1    2
 -5  SYZ         1    4    2    3
 -5  SZX         1    4    3    1
 -1        42 1.00000E+02-2.00000E+01 3.00000E+01 4.00000E+00 5.00000E+00 6.00000E+00
 -3
''')
    # FRD has yz then zx; normalize to DAT xx,yy,zz,xy,xz,yz.
    assert parse_frd(p)[42] == (100,-20,30,4,6,5)


@pytest.mark.parametrize('text', ['', ' -4  STRESS\n -1        42 1.00000E+02\n -3\n',
    ' -4  STRESS\n -1        42 1.00000E+02 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00 0.00000E+00\n'])
def test_frd_rejects_truncation(tmp_path,text):
    p=tmp_path/'bad.frd'
    p.write_text(text)
    with pytest.raises(ValueError):
        parse_frd(p)
