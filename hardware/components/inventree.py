"""Scoped, repeatable REST load. Candidate alternates never become approved substitutes."""
from __future__ import annotations

import base64
import hashlib
import json
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class API:
    def __init__(self, url, username, password):
        self.url = url.rstrip('/') + '/api/'
        self.auth = 'Basic ' + base64.b64encode(f'{username}:{password}'.encode()).decode()
        self.cache = {}

    def request(self, method, path, data=None):
        url = urljoin(self.url, path)
        if urlparse(url).netloc != urlparse(self.url).netloc:
            raise ValueError('Refusing credentials to a different API host')
        body = None if data is None else json.dumps(data).encode()
        req = Request(url, data=body, method=method,
                      headers={'Authorization':self.auth,'Content-Type':'application/json'})
        try:
            with urlopen(req, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except HTTPError as error:
            # Validation failures useful to maintainers; never include auth or request headers.
            detail = error.read(1500).decode(errors='replace')
            raise RuntimeError(f'InvenTree {method} {path}: HTTP {error.code}: {detail}') from None

    def list(self, path, refresh=False):
        if path not in self.cache or refresh:
            records, page = [], path + '?limit=250'
            while page:
                data = self.request('GET', page)
                if isinstance(data, list):
                    records.extend(data); break
                records.extend(data['results'])
                page = data.get('next')
            self.cache[path] = records
        return self.cache[path]

    def upsert(self, path, identity, values):
        matches = [r for r in self.list(path) if all(r.get(k) == v for k,v in identity.items())]
        if len(matches) > 1:
            raise ValueError(f'Ambiguous existing record at {path}: {identity}')
        data = identity | values
        if matches:
            record = matches[0]
            if any(str(record.get(k)) != str(v) for k,v in data.items()):
                updated = self.request('PATCH', f'{path}{record["pk"]}/', data)
                record.update(updated)
        else:
            record = self.request('POST', path, data)
            self.cache[path].append(record)
        return record['pk']


def parameter_values(part, template):
    values = {'DN | specifications':json.dumps(part['specs'], sort_keys=True),
              'DN | qualification':'Candidate only; engineering approval and first-board validation required.'
              if part.get('kind') == 'candidate' else 'Design baseline; board not physically validated.'}
    values.update({f'DN | {key}':str(value) for key,value in part['specs'].items()})
    for kind in ('lifecycle','rohs','reach'):
        for field,value in part[kind].items():
            values[f'DN | {kind} | {field}'] = str(value) or 'unverified'
    for field,value in template['requirements'].items():
        values[f'DN | requirement | {field}'] = str(value)
    if part.get('no_alternate_reason'):
        values['DN | no alternate reason'] = part['no_alternate_reason']
    return values


def load(api, parts, templates, bom_sha256):
    snapshot = hashlib.sha256(json.dumps({'parts':parts,'templates':templates,'bom':bom_sha256},
                                         sort_keys=True).encode()).hexdigest()
    existing = [r for r in api.list('part/') if r.get('IPN') == 'DN-ASM-DESK-NODE-A']
    if existing:
        if len(existing) != 1:
            raise ValueError('Ambiguous existing desk-node assembly')
        marker = next((r for r in api.list('parameter/template/') if r['name'] == 'DN | catalogue snapshot'), None)
        matches = [] if marker is None else [r for r in api.list('parameter/')
                    if r['model_id'] == existing[0]['pk'] and r['template'] == marker['pk']]
        if len(matches) != 1 or matches[0]['data'] != snapshot:
            raise ValueError('Changed catalogue/BOM or unmanaged assembly: use a fresh sandbox; no records were modified')
    root = api.upsert('part/category/', {'name':'Desk node catalogue'}, {'description':'Reviewed desk-node purchasing records'})
    board = api.upsert('part/', {'IPN':'DN-ASM-DESK-NODE-A'},
                       {'name':'Desk node revision A','description':'Real KiCad assembly; review holds apply',
                        'assembly':True,'component':False,'purchaseable':False,'category':root})
    expected = {'parts':{},'bom':{},'parameters':{},'manufacturers':{},'suppliers':{},'relations':{}}

    def parameters(pk, values):
        for name,data in values.items():
            tid = api.upsert('parameter/template/', {'name':name},
                             {'description':'Desk node reviewed catalogue field', 'model_type':'part'})
            pid = api.upsert('parameter/', {'model_type':'part','model_id':pk,'template':tid}, {'data':data})
            expected['parameters'][str(pid)] = data

    def component(part, ipn, category):
        pk = api.upsert('part/', {'IPN':ipn},
                        {'name':part['mpn'],'description':f'{part["family"]}: {part.get("kind", "baseline")}',
                         'category':category,'component':True,'purchaseable':part.get('kind') != 'candidate',
                         'link':part['datasheet']})
        expected['parts'][str(pk)] = ipn
        company = api.upsert('company/', {'name':part['manufacturer']},
                             {'is_manufacturer':True, 'description':'Component manufacturer'})
        mid = api.upsert('company/part/manufacturer/', {'part':pk,'manufacturer':company,'MPN':part['mpn']},
                         {'link':part['datasheet'], 'description':part.get('note','Reviewed baseline')[:250]})
        expected['manufacturers'][str(mid)] = {'part':pk, 'MPN':part['mpn']}
        parameters(pk, parameter_values(part, templates[part['family']]))
        return pk, mid

    parameters(board, {'DN | catalogue snapshot':snapshot})
    for part in parts:
        category = api.upsert('part/category/', {'name':'DN ' + part['family'], 'parent':root},
                              {'description':'Specification family: ' + part['family']})
        # Family requirements are visible on each real part, with family rule definition retained too.
        primary, manufacturer = component(part, part['ipn'], category)
        parameters(primary, {'DN | family template':json.dumps(templates[part['family']],sort_keys=True)})
        bid = api.upsert('bom/', {'part':board, 'sub_part':primary},
                         {'quantity':part['quantity'], 'reference':','.join(part['refs']),
                          'note':'Baseline only. Alternate candidates are related parts, not approved substitutes.'})
        expected['bom'][str(bid)] = {'sub_part':primary,'quantity':part['quantity'],'reference':','.join(part['refs'])}
        for source in part['suppliers']:
            supplier = api.upsert('company/', {'name':source['name']},
                                  {'is_supplier':True,'description':'Supplier; stock and price not asserted'})
            sid = api.upsert('company/part/', {'part':primary, 'supplier':supplier, 'SKU':source['sku']},
                             {'manufacturer_part':manufacturer, 'link':source['url'],
                              'description':'Board baseline source; recheck current availability'})
            expected['suppliers'][str(sid)] = {'part':primary,'SKU':source['sku']}
        for alternate in part['alternates']:
            suffix = hashlib.sha256((alternate['manufacturer'] + ':' + alternate['mpn']).encode()).hexdigest()[:10].upper()
            alt = alternate | {'family':part['family']}
            altpk, _ = component(alt, part['ipn'] + '-ALT-' + suffix, category)
            rid = api.upsert('part/related/', {'part_1':primary,'part_2':altpk},
                             {'note':('CANDIDATE ONLY: ' + alternate['note'])[:250]})
            expected['relations'][str(rid)] = {'part_1':primary,'part_2':altpk}
    parameters(board, {'DN | BOM sha256':bom_sha256})
    expected['board'] = board
    return expected


def verify(api, expected):
    """Read back actual REST records, including every spec and evidence value."""
    checks = 0
    mapping = {'parts':'part/','bom':'bom/','parameters':'parameter/',
               'manufacturers':'company/part/manufacturer/','suppliers':'company/part/','relations':'part/related/'}
    for group,path in mapping.items():
        records = {str(r['pk']):r for r in api.list(path, refresh=True)}
        for pk,values in expected[group].items():
            actual = records[pk]
            if group == 'parts':
                values = {'IPN':values}
            elif group == 'parameters':
                values = {'data':values}
            for field,value in values.items():
                got = actual[field]
                if field == 'quantity':
                    assert float(got) == value, (pk,field,got,value)
                else:
                    assert got == value, (pk,field,got,value)
                checks += 1
    assert len([r for r in api.list('bom/') if r['part'] == expected['board']]) == len(expected['bom'])
    return {'verified_fields':checks, 'component_parts':len(expected['parts']),
            'bom_lines':len(expected['bom']), 'supplier_sources':len(expected['suppliers']),
            'candidate_relations':len(expected['relations']), 'parameter_records':len(expected['parameters'])}
