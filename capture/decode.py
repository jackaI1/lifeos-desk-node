"""Decode desk-node I2C/UART captures with sigrok and explain bus faults."""
import argparse
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sys
import tempfile

from .common import MAX_SAMPLES, save_sr, sigrok


@dataclass(frozen=True)
class Annotation:
    start: int
    end: int
    text: str


def annotations(output, protocol):
    result = []
    for line in output.splitlines():
        match = re.fullmatch(r'(\d+)-(\d+) ' + protocol + r'-\d+: (.+)', line)
        if not match:
            raise ValueError(f'unrecognized {protocol} decoder output: {line[:120]}')
        start, end, text = match.groups()
        result.append(Annotation(int(start), int(end), text))
    # sigrok emits the read/write bit before its containing address byte.
    return sorted(result, key=lambda item: (item.start, item.end))


def crc8(data):
    crc = 0xff
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ (0x31 if crc & 0x80 else 0)) & 0xff
    return crc


def analyze(i2c, uart, protocols='both'):
    findings, transactions, readings, normal_nacks = [], [], [], []

    def flag(code, sample, message):
        findings.append(dict(code=code, sample=sample, message=message))

    current = None

    def finish(complete):
        nonlocal current
        if current is None:
            return
        current['complete'] = complete
        tokens = current['bytes']
        if not complete:
            flag('incomplete_transaction', current['sample'], 'I2C transaction has no STOP or repeated START before capture end')
        for index, token in enumerate(tokens):
            final_read = current.get('direction') == 'read' and index == len(tokens) - 1 and index > 0
            if current.get('address') == 0x44:
                final_read = final_read and index == 6
            if token['ack'] is None:
                flag('missing_ack', token['sample'], 'No ninth-clock ACK/NACK decoded after this byte')
            elif token['ack'] == 'NACK':
                if final_read:
                    normal_nacks.append(token['sample'])
                else:
                    flag('unexpected_nack', token['sample'], 'Receiver did not acknowledge the address or an expected data byte')
            elif final_read and current.get('address') == 0x44:
                flag('missing_final_nack', token['sample'], 'SHT31 six-byte read should end with a master NACK')
        if current.get('address') == 0x44 and current.get('direction') == 'read':
            raw = [token['value'] for token in tokens[1:]]
            if len(raw) != 6:
                flag('sensor_length', current['sample'], f'SHT31 measurement needs six bytes; decoded {len(raw)}')
            else:
                valid = True
                for offset, name in ((0, 'temperature'), (3, 'humidity')):
                    expected = crc8(raw[offset:offset + 2])
                    if raw[offset + 2] != expected:
                        valid = False
                        flag('bad_crc', tokens[offset + 3]['sample'],
                             f'SHT31 {name} CRC is 0x{raw[offset + 2]:02x}; expected 0x{expected:02x}')
                readings.append(dict(sample=current['sample'], raw=bytes(raw).hex(), crc_ok=valid,
                                     temperature_c=round(-45 + 175 * ((raw[0] << 8) | raw[1]) / 65535, 3) if valid else None,
                                     humidity_percent=round(100 * ((raw[3] << 8) | raw[4]) / 65535, 3) if valid else None))
        transactions.append(current)
        current = None

    for item in i2c:
        text = item.text
        if text in ('Start', 'Start repeat'):
            finish(text == 'Start repeat')
            current = dict(sample=item.start, bytes=[])
        elif text == 'Stop':
            finish(True)
        elif text in ('Read', 'Write'):
            continue
        elif (match := re.fullmatch(r'(Address|Data) (read|write): ([0-9A-Fa-f]{2})', text)):
            if current is None:
                flag('i2c_warning', item.start, 'Decoded byte without a START')
                continue
            kind, direction, value = match.groups()
            value = int(value, 16)
            if kind == 'Address':
                current.update(address=value, direction=direction)
            current['bytes'].append(dict(value=value, sample=item.start, ack=None))
        elif text in ('ACK', 'NACK'):
            if current and current['bytes']:
                current['bytes'][-1]['ack'] = text
            else:
                flag('i2c_warning', item.start, 'ACK/NACK without a decoded byte')
        else:
            flag('i2c_warning', item.start, text)
    finish(False)
    uart_bytes = bytearray()
    for item in uart:
        if re.fullmatch('[0-9A-Fa-f]{2}', item.text):
            uart_bytes.append(int(item.text, 16))
        elif item.text in ('Start bit', 'Stop bit'):
            continue
        else:
            flag('uart_framing' if 'Frame' in item.text else 'uart_warning', item.start, item.text)
    if protocols in ('both', 'i2c') and not any(t.get('address') == 0x44 for t in transactions):
        flag('no_sensor_traffic', 0, 'No SHT31 address 0x44 decoded; check channels and capture window')
    if protocols in ('both', 'uart') and not uart_bytes:
        flag('no_uart_traffic', 0, 'No UART bytes decoded; check TX channel and baud rate')
    return dict(ok=not findings, findings=sorted(findings, key=lambda f: f['sample']),
                i2c_transactions=transactions, sensor_readings=readings,
                normal_read_end_nacks=normal_nacks,
                uart=dict(byte_count=len(uart_bytes), hex=uart_bytes.hex(),
                          text=uart_bytes.decode('utf-8', errors='replace')))


def csv_samples(path, channels, rate):
    if not rate or rate <= 0:
        raise ValueError('CSV needs --samplerate in Hz')
    samples = bytearray()
    with path.open(newline='') as stream:
        reader = csv.reader(stream)
        header = next(reader, [])
        if not header or len(header) != len(set(header)):
            raise ValueError('CSV needs unique channel headers')
        try:
            indexes = [header.index(channel) if channel else None for channel in channels]
        except ValueError as exc:
            raise ValueError('CSV channel header not found; set --scl, --sda and --tx') from exc
        # Optional uniform timestamps, including Saleae's sampled digital export.
        time_index = next((i for i, name in enumerate(header) if name in ('Time [s]', 'time', 'Time')), None)
        previous = None
        for row in reader:
            if len(row) != len(header) or any(len(cell) > 80 for cell in row):
                raise ValueError('CSV row width or field length is invalid')
            level = 7
            for bit, index in enumerate(indexes):
                if index is not None:
                    if row[index] not in ('0', '1'):
                        raise ValueError('digital CSV levels must be 0 or 1')
                    level = (level & ~(1 << bit)) | (int(row[index]) << bit)
            if time_index is not None:
                timestamp = float(row[time_index])
                if not math.isfinite(timestamp) or (previous is not None and
                        not math.isclose(timestamp - previous, 1 / rate, rel_tol=0.01, abs_tol=1e-12)):
                    raise ValueError('CSV timestamps must be uniformly sampled at --samplerate; edge-only exports need resampling')
                previous = timestamp
            samples.append(level)
            if len(samples) > MAX_SAMPLES:
                raise ValueError('CSV exceeds 8 million samples; crop the capture')
    if not samples:
        raise ValueError('CSV contains no samples')
    return samples


def decode(path, *, samplerate=None, scl='SCL', sda='SDA', tx='TX', baudrate=115200, protocols='both'):
    path = Path(path).resolve()
    if baudrate <= 0:
        raise ValueError('baudrate must be positive')
    for channel in (scl, sda, tx):
        if not re.fullmatch(r'[A-Za-z0-9_ .-]+', channel):
            raise ValueError('channel names may contain letters, numbers, spaces, underscores, dots and hyphens')
    with tempfile.TemporaryDirectory(prefix='desk-decode-') as tmp:
        if path.suffix.lower() == '.csv':
            channels = (scl, sda, tx) if protocols == 'both' else ((scl, sda, None) if protocols == 'i2c' else (None, None, tx))
            samples = csv_samples(path, channels, samplerate)
            normalized = Path(tmp) / 'input.sr'
            save_sr(samples, normalized, samplerate)
            scl, sda, tx = 'SCL', 'SDA', 'TX'
            source = normalized
        elif path.suffix.lower() == '.sr':
            source = path
        else:
            raise ValueError('input must be .sr or uniformly sampled .csv')
        i2c, uart = [], []
        if protocols in ('both', 'i2c'):
            output = sigrok(['-i', source, '-P', f'i2c:scl={scl}:sda={sda}:address_format=shifted',
                             '-A', 'i2c=addr-data:warnings', '--protocol-decoder-samplenum'])
            i2c = annotations(output, 'i2c')
        if protocols in ('both', 'uart'):
            output = sigrok(['-i', source, '-P', f'uart:tx={tx}:baudrate={baudrate}:data_bits=8:parity=none:stop_bits=1:format=hex',
                             '-A', 'uart=tx-data:tx-warnings', '--protocol-decoder-samplenum'])
            uart = annotations(output, 'uart')
        report = analyze(i2c, uart, protocols)
        report.update(source=str(path), decoder='sigrok-cli i2c + uart', baudrate=baudrate,
                      protocols=protocols, schema_version=1)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--samplerate', type=int, help='required for CSV, in Hz; .sr carries its own rate')
    parser.add_argument('--scl', default='SCL')
    parser.add_argument('--sda', default='SDA')
    parser.add_argument('--tx', default='TX')
    parser.add_argument('--baudrate', type=int, default=115200)
    parser.add_argument('--protocols', choices=('both', 'i2c', 'uart'), default='both')
    parser.add_argument('--report', type=Path, help='save JSON report (otherwise stdout)')
    args = parser.parse_args(argv)
    try:
        report = decode(args.capture, samplerate=args.samplerate, scl=args.scl, sda=args.sda,
                        tx=args.tx, baudrate=args.baudrate, protocols=args.protocols)
        text = json.dumps(report, indent=2) + '\n'
        if args.report:
            args.report.write_text(text)
        else:
            print(text, end='')
    except (OSError, ValueError, csv.Error) as exc:
        print(f'capture: {exc}', file=sys.stderr)
        return 2
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
