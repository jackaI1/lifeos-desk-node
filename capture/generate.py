"""Turn existing Scheme/C replay output into synthetic logic-analyzer samples."""
import argparse
import csv
import json
from pathlib import Path
import sys

from .common import MAX_SAMPLES, save_sr

RATE = 2_000_000
BAUD = 115200
FAULTS = ('nack', 'missing-ack', 'humidity-crc', 'uart-framing')


class Wave:
    def __init__(self):
        self.samples = bytearray()
        self.level = 7  # SCL, SDA and TX idle high

    def hold(self, count, scl=None, sda=None, tx=None):
        for bit, value in enumerate((scl, sda, tx)):
            if value is not None:
                self.level = (self.level & ~(1 << bit)) | (int(value) << bit)
        if len(self.samples) + count > MAX_SAMPLES:
            raise ValueError('capture exceeds 8 million samples; shorten the scenario')
        self.samples.extend(bytes([self.level]) * count)

    def start(self):
        self.hold(10, scl=1, sda=1)
        self.hold(10, sda=0)
        self.hold(10, scl=0)

    def stop(self):
        self.hold(10, scl=0, sda=0)
        self.hold(10, scl=1)
        self.hold(10, sda=1)

    def byte(self, value, ack=True, omit_ack=False):
        for bit in range(7, -1, -1):
            self.hold(10, scl=0, sda=(value >> bit) & 1)
            self.hold(10, scl=1)
        self.hold(10, scl=0)
        if not omit_ack:
            self.hold(10, sda=not ack)
            self.hold(10, scl=1)
            self.hold(10, scl=0)

    def uart(self, data, corrupt=False):
        # Round absolute bit boundaries to avoid baud drift from integer truncation.
        tick = 0
        for index, value in enumerate(data):
            bits = [0, *[(value >> b) & 1 for b in range(8)],
                    0 if corrupt and index == 0 else 1, 1, 1]
            for bit in bits:
                length = round((tick + 1) * RATE / BAUD) - round(tick * RATE / BAUD)
                self.hold(length, tx=bit)
                tick += 1


def generate(wire, uart_log, faults=()):
    lines = wire.splitlines()
    if not lines or lines[0] != 'DESK_REPLAY_V1' or not 1 <= len(lines[1:]) <= 4096:
        raise ValueError('expected existing DESK_REPLAY_V1 scenario output')
    commands = lines[1:]
    logs = uart_log.splitlines(keepends=True)
    if len(commands) != len(logs) or any(not x.startswith(b'desk ') or not x.endswith(b'\r\n') for x in logs):
        raise ValueError('UART log must come from desk-replay --uart-log for the same scenario')
    wave = Wave()
    wave.hold(100)
    injected = False
    sensor_frames = []
    last_sample = max((i for i, command in enumerate(commands) if command != 'U'), default=-1)
    for position, (command, log) in enumerate(zip(commands, logs)):
        if command != 'U':
            if len(command) != 14 or not command.startswith('S '):
                raise ValueError('invalid scenario sample')
            raw = bytearray.fromhex(command[2:])
            active = set(faults) if not injected else set()
            active.discard('missing-ack')
            if 'missing-ack' in faults and position == last_sample:
                active.add('missing-ack')
            if 'humidity-crc' in active:
                raw[5] ^= 1
            wave.start()
            wave.byte(0x88, ack='nack' not in active)
            wave.byte(0x24)
            wave.byte(0x00)
            wave.stop()
            wave.hold(RATE // 50)  # Firmware waits 20 ms for the measurement.
            wave.start()
            wave.byte(0x89)
            for index, byte in enumerate(raw):
                wave.byte(byte, ack=index < 5,
                          omit_ack='missing-ack' in active and index == 5)
            if 'missing-ack' not in active:
                wave.stop()
            sensor_frames.append(raw.hex())
            injected = True
        else:
            active = set()
        wave.hold(100)
        wave.uart(log, corrupt='uart-framing' in active)
        wave.hold(100, tx=1)
    if faults and not injected:
        raise ValueError('fault injection needs at least one sensor sample')
    return wave.samples, {'synthetic': True, 'samplerate': RATE, 'baudrate': BAUD,
                          'injected_faults': list(faults), 'sensor_frames': sensor_frames,
                          'samples': len(wave.samples), 'uart_bytes': len(uart_log)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wire', type=Path)
    parser.add_argument('--uart-log', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='.sr or uniform sample .csv')
    parser.add_argument('--fault', choices=FAULTS, action='append', default=[])
    args = parser.parse_args(argv)
    try:
        if args.wire.stat().st_size > 65536 or args.uart_log.stat().st_size > 1_000_000:
            raise ValueError('scenario or UART log too large')
        samples, manifest = generate(args.wire.read_text(), args.uart_log.read_bytes(), args.fault)
        if args.output.suffix == '.sr':
            save_sr(samples, args.output, RATE)
        elif args.output.suffix == '.csv':
            with args.output.open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['SCL', 'SDA', 'TX'])
                writer.writerows([(b & 1, (b >> 1) & 1, (b >> 2) & 1) for b in samples])
        else:
            raise ValueError('output must end in .sr or .csv')
        args.output.with_suffix(args.output.suffix + '.json').write_text(json.dumps(manifest, indent=2) + '\n')
    except (OSError, ValueError) as exc:
        print(f'capture: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
