import json
from pathlib import Path
import copy
import pytest

from hardware.components.core import parse_bom, prepare, check_alternate
from hardware.components.inventree import parameter_values

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT/'hardware/components'


def inputs():
    with (ROOT/'hardware/bom.csv').open() as stream:
        bom = parse_bom(stream)
    return bom, json.loads((DATA/'catalog.json').read_text()), json.loads((DATA/'templates.json').read_text())


def test_real_board_every_reference_and_mpn_is_accounted_for():
    bom, catalog, templates = inputs()
    parts = prepare(bom, catalog, templates)
    assert len(parts) == 19
    assert sum(p['quantity'] for p in parts) == 31
    assert len({r for p in parts for r in p['refs']}) == 31
    assert len({p['ipn'] for p in parts}) == 19
    assert sum(len(p['alternates']) for p in parts) >= 9
    for p in parts:
        assert p['specs'] and p['datasheet']
        assert all(k in templates[p['family']]['requirements'] for k in ['fire_smoke_toxicity','shock_vibration'])
        for a in p['alternates']:
            assert not check_alternate(p,a,templates[p['family']])
            assert a['kind'] == 'candidate'
            assert a['note']


def test_undated_lifecycle_cannot_hide_reported_nrnd():
    bom, catalog, templates = inputs()
    parts = prepare(bom, catalog, templates)
    capacitor = next(p for p in parts if p['mpn']=='CL21A226MOQNNNE')
    assert capacitor['lifecycle']['status']=='unverified'
    assert capacitor['lifecycle']['reported_status']=='nrnd'


def test_all_evidence_has_explicit_status_and_missing_documents_never_pass():
    bom, catalog, templates = inputs()
    for p in prepare(bom,catalog,templates):
        for item in [p,*p['alternates']]:
            for kind in ['rohs','reach','lifecycle']:
                record=item[kind]
                assert record['status']
                if record['status'] != 'unverified':
                    assert record['document_date'] and record['checked_on'] and record['scope']
                    assert record['source_url'].startswith('https://')
        params=parameter_values(p,templates[p['family']])
        assert params['DN | rohs | status'] == p['rohs']['status']
        assert 'DN | requirement | fire_smoke_toxicity' in params


def test_catalogue_refuses_added_or_removed_board_part():
    bom, catalog, templates=inputs()
    catalog['parts'].pop()
    with pytest.raises(ValueError,match='drift'):
        prepare(bom,catalog,templates)


@pytest.mark.parametrize('field,value', [('manufacturer',''),('mpn',' '),('datasheet',''),('current_a',float('nan')),('current_a','0.8'),('current_a',True)])
def test_primary_identity_and_ratings_are_validated_without_alternates(field,value):
    bom,catalog,templates=inputs()
    primary=next(p for p in catalog['parts'] if p['family']=='regulator')
    if field in primary['specs']:
        primary['specs'][field]=value
    else:
        primary[field]=value
    with pytest.raises(ValueError):
        prepare(bom,catalog,templates)
