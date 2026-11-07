"""Decode captured custom BLE characteristic bytes or validate WiFi RSSI logs."""
import argparse
import binascii
import json
import re
import struct


def decode(payload):
    if len(payload) != 16: raise ValueError('BLE sample must be 16 bytes')
    version, flags, temperature, humidity, sequence, crc = struct.unpack('<BBiIIH', payload)
    if version != 1 or flags or binascii.crc_hqx(payload[:14], 0xffff) != crc:
        raise ValueError('unsupported schema or bad CRC')
    if not -45000 <= temperature <= 125000 or humidity > 100000:
        raise ValueError('sensor out of range')
    return dict(sequence=sequence, temperature_mc=temperature, humidity_mpermil=humidity)


def wifi(line):
    match = re.search(r'WIFI connected rssi=(-?\d+) attempts=(\d+)', line)
    if not match or not -127 <= int(match[1]) <= 0 or not 0 <= int(match[2]) <= 6:
        raise ValueError('invalid WiFi RSSI/retry log')
    return dict(rssi_dbm=int(match[1]), attempts=int(match[2]))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', help='text file, hex BLE payload per line or WIFI connected log')
    a=p.parse_args()
    with open(a.capture) as stream:
        for line in stream:
            print(json.dumps(wifi(line) if 'WIFI' in line else decode(bytes.fromhex(line))))


if __name__ == '__main__': main()
