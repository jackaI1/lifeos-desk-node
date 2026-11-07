"""Replay bounded JSONL recordings over python-can virtual or Linux SocketCAN."""
import argparse
import json
import math
import time
import uuid
from contextlib import ExitStack
import can
from .monitor import Monitor, make_frame


def record(frame, timestamp):
    return dict(time=timestamp, id=frame.arbitration_id, data=frame.data.hex(),
                fd=frame.is_fd, brs=frame.bitrate_switch, dlc=frame.dlc,
                extended=frame.is_extended_id)


def generate(path, faults=False):
    rows = [record(make_frame(20 + i / 10, i, heater=35, fan=40), i / 10) for i in range(10)]
    rows += [record(make_frame(21, i, fd=True), 1 + i / 10) for i in range(3)]
    if faults:
        rows[2]['data'] = rows[2]['data'][:-2]  # wrong payload length
        rows[4]['id'] = 0x777
        rows[6]['data'] = 'ff' + rows[6]['data'][2:]  # bad checksum
        rows[8] = record(make_frame(21, 42), .8)  # counter gap
        rows[-1]['time'] = 5.0  # prolonged silence on primary ID
    with open(path, 'w', encoding='utf8') as out:
        for row in rows:
            out.write(json.dumps(row) + '\n')


def load(path):
    previous = -math.inf
    with open(path, encoding='utf8') as stream:
        for i, line in enumerate(stream):
            if i >= 100000 or len(line) > 1024:
                raise ValueError('recording exceeds 100000 frames or 1024 bytes per line')
            row = json.loads(line)
            timestamp = row['time']
            if isinstance(timestamp, bool) or not math.isfinite(timestamp) or timestamp < previous or timestamp < 0:
                raise ValueError('timestamps must be finite, nonnegative and ordered')
            previous = timestamp
            data = bytes.fromhex(row['data'])
            if len(data) > 64:
                raise ValueError('CAN payload exceeds 64 bytes')
            # check=False lets recorded invalid DLCs reach the diagnostic layer.
            yield timestamp, can.Message(arbitration_id=row['id'], data=data,
                is_extended_id=row.get('extended', False), is_fd=row.get('fd', False),
                bitrate_switch=row.get('brs', row.get('fd', False)), dlc=row.get('dlc', len(data)))


def replay(path, *, interface='virtual', channel=None, timeout=2.0, tail=0.0):
    monitor = Monitor(timeout=timeout)
    results = []
    now = 0.0
    channel = channel or ('desk-' + uuid.uuid4().hex if interface == 'virtual' else 'vcan0')
    with ExitStack() as stack:
        options = dict(interface=interface, channel=channel, fd=True, ignore_config=True)
        tx = stack.enter_context(can.Bus(**options))
        rx = stack.enter_context(can.Bus(**options))
        for now, frame in load(path):
            # The OS cannot carry inconsistent DLC/payload combinations. Diagnose
            # such recordings before transport; send all representable frames.
            if frame.dlc != len(frame.data):
                received = frame
            else:
                tx.send(frame, timeout=1)
                received = rx.recv(1)
                if received is None:
                    raise TimeoutError('replay bus did not deliver the frame')
            result = monitor.process(received, now)
            result.update(time=now, id=hex(frame.arbitration_id))
            results.append(result)
    if not math.isfinite(tail) or tail < 0:
        raise ValueError('tail must be finite and nonnegative')
    return {'frames': results, 'rates': {hex(k): v for k, v in monitor.rates().items()},
            'summary': monitor.summary(now + tail)}


def listen(channel, seconds, timeout):
    monitor = Monitor(timeout=timeout, start=time.monotonic())
    deadline = time.monotonic() + seconds
    with can.Bus(interface='socketcan', channel=channel, fd=True, ignore_config=True) as bus:
        while time.monotonic() < deadline:
            frame = bus.recv(min(.1, max(0, deadline - time.monotonic())))
            now = time.monotonic()
            if frame is not None:
                print(json.dumps(monitor.process(frame, now)))
            else:
                monitor.outputs(now)  # silence is checked even when no frames arrive
    return monitor.summary(time.monotonic())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', nargs='?')
    parser.add_argument('--generate', metavar='PATH')
    parser.add_argument('--faults', action='store_true')
    parser.add_argument('--interface', choices=['virtual', 'socketcan'], default='virtual')
    parser.add_argument('--channel')
    parser.add_argument('--timeout', type=float, default=2)
    parser.add_argument('--tail', type=float, default=0, help='extra logical silence after recording')
    parser.add_argument('--listen', type=float, metavar='SECONDS')
    args = parser.parse_args()
    try:
        if args.generate:
            generate(args.generate, args.faults)
            return
        if args.listen is not None:
            if not math.isfinite(args.listen) or not 0 < args.listen <= 3600:
                raise ValueError('listen duration must be in (0, 3600] seconds')
            result = listen(args.channel or 'vcan0', args.listen, args.timeout)
        elif args.log:
            result = replay(args.log, interface=args.interface, channel=args.channel,
                            timeout=args.timeout, tail=args.tail)
        else:
            parser.error('provide a log, --generate or --listen')
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, KeyError, OSError, can.CanError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
