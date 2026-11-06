"""Validate a point-to-point harness before producing manufacturing sheets."""
import json
import math
import sys

# Conservative project planning limits, not a substitute for wire manufacturer ratings.
LIMITS = {20: 1.0, 22: 0.7, 24: 0.5, 26: 0.3, 28: 0.2}

def validate(data):
    errors = []
    connectors = data.get('connectors', {})
    wires = data.get('wires', [])
    if not isinstance(connectors, dict) or not connectors:
        errors.append('connectors must be a nonempty object')
        connectors = {}
    if not isinstance(wires, list) or not wires:
        return errors + ['wires must be a nonempty list']
    pins, ids, grounded = {}, set(), set()
    for index, w in enumerate(wires, 1):
        if not isinstance(w, dict):
            errors.append(f'wire {index}: expected object')
            continue
        label = w.get('id')
        if not isinstance(label, str) or not label.strip():
            errors.append(f'wire {index}: missing id')
        elif label in ids:
            errors.append(f'duplicate wire id {label}')
        else:
            ids.add(label)
        for field in ('net', 'color'):
            if not isinstance(w.get(field), str) or not w[field].strip():
                errors.append(f'wire {index}: missing {field}')
        for end in ('from', 'to'):
            endpoint = w.get(end)
            if not isinstance(endpoint, list) or len(endpoint) != 2 or any(not isinstance(x, str) or not x.strip() for x in endpoint):
                errors.append(f'wire {index}: invalid {end} endpoint')
                continue
            conn, pin = endpoint
            if conn not in connectors:
                errors.append(f'wire {index}: unknown connector {conn}')
            key = (conn, pin)
            if key in pins:
                errors.append(f'pin {conn}:{pin} used by both {pins[key]} and {label}')
            else:
                pins[key] = label
            if w.get('net') == 'GND':
                grounded.add(conn)
        length = w.get('length_mm')
        current = w.get('current_a')
        awg = w.get('awg')
        if isinstance(length, bool) or not isinstance(length, (int, float)) or not math.isfinite(length) or length <= 0:
            errors.append(f'wire {index}: length_mm must be positive and finite')
        if isinstance(current, bool) or not isinstance(current, (int, float)) or not math.isfinite(current) or current < 0:
            errors.append(f'wire {index}: current_a must be nonnegative and finite')
        elif isinstance(awg, bool) or not isinstance(awg, int) or awg not in LIMITS:
            errors.append(f'wire {index}: unsupported AWG; use {sorted(LIMITS)}')
        elif current > LIMITS[awg]:
            errors.append(f'wire {index}: AWG {awg} too small for {current} A (limit {LIMITS[awg]} A)')
    for conn, spec in connectors.items():
        if not isinstance(spec, dict):
            errors.append(f'{conn}: connector settings must be an object')
        elif spec.get('requires_ground') and conn not in grounded:
            errors.append(f'{conn}: missing ground')
    return errors

def load(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError('pin map must be an object')
    return data

def main():
    if len(sys.argv) != 2:
        print('Usage: python -m harness.check MAP.json', file=sys.stderr)
        return 2
    try:
        errors = validate(load(sys.argv[1]))
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('Pin map OK')
    return 0

if __name__ == '__main__':
    sys.exit(main())
