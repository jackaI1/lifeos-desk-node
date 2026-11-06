import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import pytest
from hardware.components.core import parse_bom, prepare
from hardware.components.inventree import API, load, parameter_values, verify


def test_upsert_exact_identity_is_repeatable():
    api = API('http://localhost:1234', 'demo', 'temporary')
    calls = []
    def request(method, path, data=None):
        calls.append((method,path,data))
        if method == 'GET': return {'results':[], 'next':None}
        return {'pk':1} | data
    api.request = request
    assert api.upsert('part/', {'IPN':'DN-X'}, {'name':'Part'}) == 1
    assert api.upsert('part/', {'IPN':'DN-X'}, {'name':'Part'}) == 1
    assert [c[0] for c in calls] == ['GET','POST']
    api.upsert('part/', {'IPN':'DN-X'}, {'name':'Updated'})
    assert calls[-1][0] == 'PATCH'


def test_pagination_reads_all_pages():
    api = API('http://localhost:1234', 'demo', 'temporary')
    pages = iter([{'results':[{'pk':1}], 'next':'http://localhost:1234/api/part/?offset=1'},
                  {'results':[{'pk':2}], 'next':None}])
    api.request = lambda *args:next(pages)
    assert len(api.list('part/')) == 2


def test_refuses_auth_to_cross_host_pagination():
    api = API('http://localhost:1234', 'demo', 'temporary')
    with pytest.raises(ValueError, match='different API host'):
        api.request('GET','https://attacker.invalid/api/part/')


def test_ambiguous_existing_part_is_not_overwritten():
    api = API('http://localhost:1234', 'demo', 'temporary')
    api.cache['part/'] = [{'pk':1,'IPN':'DN-X'}, {'pk':2,'IPN':'DN-X'}]
    with pytest.raises(ValueError, match='Ambiguous'):
        api.upsert('part/', {'IPN':'DN-X'}, {})


def test_withdrawn_candidate_refuses_changed_catalogue_before_any_mutation():
    """A changed load must not leave a withdrawn candidate linked in the database."""
    class MemoryAPI:
        def __init__(self):
            self.records = {}
            self.next_pk = 1

        def list(self, path, refresh=False):
            return self.records.get(path, [])

        def upsert(self, path, identity, values):
            rows = self.records.setdefault(path, [])
            for row in rows:
                if all(row.get(key) == value for key, value in identity.items()):
                    row.update(deepcopy(values))
                    return row['pk']
            row = {'pk': self.next_pk} | deepcopy(identity) | deepcopy(values)
            self.next_pk += 1
            rows.append(row)
            return row['pk']

    root = Path(__file__).resolve().parents[3]
    data = root / 'hardware/components'
    with (root / 'hardware/bom.csv').open() as stream:
        bom = parse_bom(stream)
    templates = json.loads((data / 'templates.json').read_text())
    parts = prepare(bom, json.loads((data / 'catalog.json').read_text()), templates)
    api = MemoryAPI()
    initial = load(api, parts, templates, 'a' * 64)
    verify(api, initial)
    before = deepcopy(api.records)
    next_pk = api.next_pk
    changed = deepcopy(parts)
    item = next(part for part in changed if part['alternates'])
    item['alternates'].pop()
    item['no_alternate_reason'] = 'Candidate withdrawn after engineering review'

    with pytest.raises(ValueError):
        load(api, changed, templates, 'a' * 64)

    assert api.records == before
    assert api.next_pk == next_pk
