"""Decode Environmental Sensing (0x181A) temperature and humidity bytes read from the desk node.

Usage:
    python3 firmware/tools/ess_decode.py temperature "59 08"   # 0x2A6E: 21.37 degC
    python3 firmware/tools/ess_decode.py humidity "a0 11"      # 0x2A6F: 45.12 %RH
"""
import argparse
import struct


def _bytes(text):
    payload = bytes.fromhex(text.replace(' ', ''))
    if len(payload) != 2:
        raise ValueError('Environmental Sensing values are exactly 2 bytes')
    return payload


def temperature(text):
    (value,) = struct.unpack('<h', _bytes(text))
    if not -4500 <= value <= 12500:
        raise ValueError('temperature outside the service range')
    return value / 100


def humidity(text):
    (value,) = struct.unpack('<H', _bytes(text))
    if value > 10000:
        raise ValueError('humidity outside the service range')
    return value / 100


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('kind', choices=['temperature', 'humidity'])
    parser.add_argument('hex', help='two bytes as read from the phone, e.g. "59 08"')
    args = parser.parse_args()
    value = temperature(args.hex) if args.kind == 'temperature' else humidity(args.hex)
    print(f'{args.kind}={value:.2f} {"degC" if args.kind == "temperature" else "%RH"}')


if __name__ == '__main__':
    main()
