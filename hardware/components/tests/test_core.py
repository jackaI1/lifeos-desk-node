import copy
import csv
import io
from pathlib import Path

import pytest

from hardware.components.core import (parse_bom, internal_number, evidence, check_alternate, prepare)

HEADER = 'Designator,Value,Footprint,LCSC,MPN,Qty\n'

def test_bom_groups_repeated_mpn_and_preserves_refs():
    rows = parse_bom(io.StringIO(HEADER + '"R2,R1",10k,R0603,C1,R-10K,2\nR3,10k,R0603,C1,R-10K,1\n'))
    assert rows[0]['refs'] == ['R1', 'R2', 'R3']
    assert rows[0]['quantity'] == 3

@pytest.mark.parametrize('body', [
    '"R1,R2",10k,R0603,C1,R-10K,1\n',
    'R1,10k,R0603,C1,R-10K,1\nR1,10k,R0603,C1,R-10K,1\n',
    'R1-R3,10k,R0603,C1,R-10K,3\n',
    'R1,10k,R0603,C1,,1\n',
    'R1,10k,R0603,C1,R-10K,0\n',
    'R1,10k,R0603,C1,R-10K,1\nR2,10k,R0805,C1,R-10K,1\n',
])
def test_rejects_ambiguous_bom(body):
    with pytest.raises(ValueError):
        parse_bom(io.StringIO(HEADER + body))

def test_requires_exact_headers():
    with pytest.raises(ValueError):
        parse_bom(io.StringIO('Reference,Qty\nR1,1\n'))

def test_numbering_is_structured_and_reference_independent():
    assert internal_number('resistor', 'res-10k') == 'DN-RES-RES-10K'
    assert internal_number('resistor', 'res-10k') != internal_number('resistor', 'res-1k')
    with pytest.raises(ValueError):
        internal_number('resistor', '../bad')
    with pytest.raises(ValueError):
        internal_number('unknown', 'thing')

def test_missing_and_undated_evidence_stays_unverified():
    assert evidence({}, 'rohs')['status'] == 'unverified'
    claim = {'status':'compliant','source_url':'https://maker.example/rohs.pdf','checked_on':'2026-11-06'}
    assert evidence(claim, 'rohs')['status'] == 'unverified'
    claim.update(document_date='2026-01-02', scope='Exact orderable part', note='Manufacturer declaration')
    assert evidence(claim, 'rohs')['status'] == 'compliant'
    claim['status'] = 'unknown'
    with pytest.raises(ValueError):
        evidence(claim, 'rohs')

def test_resistor_alternate_enforces_ratings_and_identity():
    template = {'alternate_rules': {'resistance_ohm':'equal','package':'equal','tolerance_pct':'at_most','power_w':'at_least'}}
    primary = {'specs': {'resistance_ohm':10000, 'package':'0603', 'tolerance_pct':1, 'power_w':0.1}}
    alt = {'manufacturer':'Other', 'mpn':'R10', 'datasheet':'https://maker.example/r.pdf', 'specs':dict(primary['specs'])}
    assert check_alternate(primary, alt, template) == []
    for key, value in [('resistance_ohm',4700), ('package','0805'), ('power_w',0.05), ('tolerance_pct',5)]:
        bad = copy.deepcopy(alt); bad['specs'][key] = value
        assert check_alternate(primary, bad, template)
    del alt['specs']['package']
    assert check_alternate(primary, alt, template)

@pytest.mark.parametrize('bad', [float('nan'), float('inf'), True, '0.1'])
def test_numeric_alternate_fields_cannot_bypass_checks(bad):
    primary = {'specs':{'power_w':0.1}}
    alt = {'manufacturer':'Other','mpn':'X','datasheet':'https://maker.example/x.pdf','specs':{'power_w':bad}}
    assert check_alternate(primary, alt, {'alternate_rules':{'power_w':'at_least'}})

def test_prepare_fails_for_missing_catalogue_item():
    rows = parse_bom(io.StringIO(HEADER + 'R1,10k,R0603,C1,R-10K,1\n'))
    with pytest.raises(ValueError, match='catalog'):
        prepare(rows, {'parts':[]}, {})


def test_placements_match_every_fitted_reference_and_package():
    from hardware.components.core import validate_placements
    bom=parse_bom(io.StringIO(HEADER+'R1,10k,Resistor_SMD:R_0603,C1,R-10K,1\n'))
    valid='Ref,Val,Package,PosX,PosY,Rot,Side\nR1,10k,R_0603,10,20,90,top\n'
    validate_placements(io.StringIO(valid),bom)
    for bad in [valid.replace('R1,10k','R2,10k'),valid.replace('R_0603,10','R_0805,10'),
                valid.replace('10,20,90','nan,20,90'),valid+valid.splitlines()[1]+'\n']:
        with pytest.raises(ValueError):
            validate_placements(io.StringIO(bad),bom)
