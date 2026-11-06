"""Strict boundary between the KiCad BOM and the reviewed purchasing catalogue."""
from __future__ import annotations

import copy
import csv
from datetime import date
import math
import re
from urllib.parse import urlparse

FAMILIES = {'resistor':'RES', 'capacitor':'CAP', 'tvs':'TVS', 'led':'LED',
            'fuse':'FUS', 'connector':'CON', 'switch':'SWT', 'module':'MOD',
            'regulator':'REG', 'sensor':'SEN'}
HEADERS = {'Designator', 'Value', 'Footprint', 'LCSC', 'MPN', 'Qty'}


def ref_key(ref):
    match = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', ref)
    if not match:
        raise ValueError(f'Invalid or ranged reference: {ref!r}; export without ranges')
    return match[1], int(match[2])


def parse_bom(stream):
    reader = csv.DictReader(stream)
    if not reader.fieldnames or set(reader.fieldnames) != HEADERS or len(reader.fieldnames) != len(HEADERS):
        raise ValueError('BOM requires exactly Designator,Value,Footprint,LCSC,MPN,Qty')
    groups, seen = {}, set()
    for line, row in enumerate(reader, 2):
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f'Malformed CSV row {line}')
        row = {k:v.strip() for k,v in row.items()}
        if any(not row[k] for k in HEADERS):
            raise ValueError(f'Missing BOM field at row {line}')
        refs = [r.strip() for r in row['Designator'].split(',')]
        for ref in refs:
            ref_key(ref)
            if ref in seen:
                raise ValueError(f'Duplicate reference: {ref}')
            seen.add(ref)
        if not row['Qty'].isdigit() or int(row['Qty']) != len(refs):
            raise ValueError(f'Quantity differs from explicit references at row {line}')
        mpn = row['MPN']
        if mpn in groups:
            part = groups[mpn]
            if part['footprint'] != row['Footprint'] or part['lcsc'] != row['LCSC']:
                raise ValueError(f'Conflicting footprint/supplier for {mpn}')
            if part['value'] != row['Value']:
                part['value'] = '-- mixed values --'
            part['refs'].extend(refs)
            part['quantity'] += len(refs)
        else:
            groups[mpn] = {'schematic_mpn':mpn, 'refs':refs, 'quantity':len(refs),
                           'footprint':row['Footprint'], 'lcsc':row['LCSC'], 'value':row['Value']}
    if not groups:
        raise ValueError('Empty fitted BOM')
    for part in groups.values():
        part['refs'].sort(key=ref_key)
    return sorted(groups.values(), key=lambda p:ref_key(p['refs'][0]))


def internal_number(family, key):
    if family not in FAMILIES or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key):
        raise ValueError(f'Invalid internal part family/key: {family}/{key}')
    return f'DN-{FAMILIES[family]}-{key.upper()}'


def evidence(record, kind):
    """Downgrade unsupported claims; review dates never replace declaration dates."""
    result = {k:record.get(k, '') for k in
              ('status','source_url','document_date','checked_on','scope','note')}
    result['status'] = result['status'] or 'unverified'
    allowed = {'active','nrnd','eol','unverified'} if kind == 'lifecycle' else {'compliant','noncompliant','unverified'}
    if result['status'] not in allowed:
        raise ValueError(f'Unknown {kind} status: {result["status"]}')
    supported = bool(result['scope'] and urlparse(result['source_url']).scheme == 'https')
    try:
        published, checked = date.fromisoformat(result['document_date']), date.fromisoformat(result['checked_on'])
        supported &= published <= checked <= date.today()
    except (ValueError, TypeError):
        supported = False
    if result['status'] != 'unverified' and not supported:
        result['reported_status'] = result['status']
        result['note'] = (result['note'] + ' Missing dated, scoped manufacturer evidence; claim held unverified.').strip()
        result['status'] = 'unverified'
    return result


def check_alternate(primary, alternate, template):
    errors = []
    if any(not alternate.get(k) for k in ('manufacturer','mpn','datasheet')):
        errors.append('missing manufacturer, MPN or datasheet')
    rules = template.get('alternate_rules', {})
    if not rules:
        return errors + ['no comparison rules for family']
    a, b = primary['specs'], alternate.get('specs', {})
    for field, rule in rules.items():
        if field not in a or field not in b:
            errors.append(f'{field}: missing parameter'); continue
        x, y = a[field], b[field]
        if isinstance(x, (int,float)) and not isinstance(x, bool):
            if not isinstance(y, (int,float)) or isinstance(y, bool) or not math.isfinite(y) or not math.isfinite(x):
                errors.append(f'{field}: finite numeric value required'); continue
        elif rule != 'equal':
            errors.append(f'{field}: numeric baseline required'); continue
        if rule not in {'equal','at_least','at_most'}:
            raise ValueError(f'Invalid comparison rule {rule}')
        ok = (x == y if rule == 'equal' else y >= x if rule == 'at_least' else y <= x)
        if not ok:
            errors.append(f'{field}: {y} fails {rule} {x}')
    return errors


def prepare(bom, catalog, templates):
    items = catalog['parts']
    indexed = {p['schematic_mpn']:p for p in items}
    if len(indexed) != len(items):
        raise ValueError('Duplicate catalogue MPN')
    if set(indexed) != {p['schematic_mpn'] for p in bom}:
        raise ValueError('BOM/catalogue drift: every fitted MPN must have exactly one catalogue entry')
    prepared, numbers = [], set()
    for row in bom:
        item = copy.deepcopy(indexed[row['schematic_mpn']])
        item.update(row)
        item['ipn'] = internal_number(item['family'], item['key'])
        if item['ipn'] in numbers:
            raise ValueError('Duplicate internal part number')
        numbers.add(item['ipn'])
        template = templates[item['family']]
        for identity in ('manufacturer','mpn','datasheet'):
            if not isinstance(item.get(identity), str) or not item[identity].strip():
                raise ValueError(f'Missing primary identity {identity}: {item["ipn"]}')
        for field,value in item.get('specs', {}).items():
            if field in {'package','pinout','interface','dielectric'}:
                if not isinstance(value,str) or not value.strip():
                    raise ValueError(f'Missing text specification {field}')
            elif isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f'Invalid numeric specification {field}: {item["ipn"]}')
        if not item.get('specs') or not item.get('datasheet'):
            raise ValueError(f'Missing specifications/datasheet: {item["ipn"]}')
        for field in template['alternate_rules']:
            if field not in item['specs']:
                raise ValueError(f'Missing {field}: {item["ipn"]}')
        if not any(s['name'] == 'LCSC' and s['sku'] == row['lcsc'] for s in item['suppliers']):
            raise ValueError(f'Supplier identity differs from schematic: {item["ipn"]}')
        for kind in ('lifecycle','rohs','reach'):
            item[kind] = evidence(item.get(kind, {}), kind)
        for alternate in item['alternates']:
            if alternate['mpn'] == item['mpn'] and alternate['manufacturer'] == item['manufacturer']:
                raise ValueError('An alternate must be a distinct manufacturer part')
            problems = check_alternate(item, alternate, template)
            if problems:
                raise ValueError(f'Incompatible alternate for {item["ipn"]}: {problems}')
            alternate['kind'] = 'candidate'
            for kind in ('lifecycle','rohs','reach'):
                alternate[kind] = evidence(alternate.get(kind, {}), kind)
        if not item['alternates'] and not item.get('no_alternate_reason'):
            raise ValueError(f'Explain absent alternate: {item["ipn"]}')
        prepared.append(item)
    return prepared


def validate_placements(stream, parts):
    """Check the actual KiCad position export against fitted BOM identities."""
    reader = csv.DictReader(stream)
    expected_headers = {'Ref','Val','Package','PosX','PosY','Rot','Side'}
    if not reader.fieldnames or set(reader.fieldnames) != expected_headers:
        raise ValueError('Placement file must be a KiCad CSV position export')
    expected = {ref:p for p in parts for ref in p['refs']}
    seen = set()
    for row in reader:
        ref = row.get('Ref')
        if ref not in expected or ref in seen:
            raise ValueError(f'Unexpected or duplicate placement reference: {ref}')
        seen.add(ref)
        part=expected[ref]
        if row['Package'] != part['footprint'].split(':')[-1]:
            raise ValueError(f'Placement package differs from BOM: {ref}')
        # Buttons have mixed labels after MPN grouping; reference/package is their identity.
        if part['value'] != '-- mixed values --' and row['Val'] != part['value']:
            raise ValueError(f'Placement value differs from BOM: {ref}')
        if row['Side'] not in {'top','bottom'}:
            raise ValueError(f'Invalid placement side: {ref}')
        try:
            if not all(math.isfinite(float(row[k])) for k in ('PosX','PosY','Rot')):
                raise ValueError('nonfinite')
        except (ValueError,TypeError):
            raise ValueError(f'Nonfinite or missing placement coordinate: {ref}') from None
    if seen != set(expected):
        raise ValueError('Placement references do not cover the fitted BOM')
