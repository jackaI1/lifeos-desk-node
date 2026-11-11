"""Send sensor transfers to the iCEBreaker board and print its counts.

The board takes a transfer as one length byte (1 to 255) followed by that many
sensor bytes, and replies with six bytes: good, bad and truncated frame counts,
each as a high byte then a low byte.

Examples (replace the port with the one your computer shows for the board):

    python3 board/icebreaker/host.py --port /dev/tty.usbserial-XXXX --demo
    python3 board/icebreaker/host.py --port /dev/ttyUSB0 --hex 6a5b 8c2d ...

The packing and reply functions do not need the board, so the tests run them
on any computer. Only `main` opens the serial port, and it imports pyserial
only when it is needed.
"""
import argparse
import struct
import sys

LENGTH_MAX = 255


def crc8(data):
    """The SHT31 checksum: polynomial 0x31, initial value 0xFF, no final XOR."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def make_frame(temp_word, hum_word):
    """Six bytes as the sensor sends them: word, checksum, word, checksum."""
    temp = struct.pack('>H', temp_word)
    hum = struct.pack('>H', hum_word)
    return bytes([temp[0], temp[1], crc8(temp), hum[0], hum[1], crc8(hum)])


def pack_transfer(payload):
    """One transfer: a length byte, then the payload bytes."""
    if not 1 <= len(payload) <= LENGTH_MAX:
        raise ValueError(f'a transfer carries 1 to {LENGTH_MAX} bytes, got {len(payload)}')
    return bytes([len(payload)]) + bytes(payload)


def parse_reply(reply):
    """Six reply bytes to (good, bad, truncated) counts."""
    if len(reply) != 6:
        raise ValueError(f'the board replies with 6 bytes, got {len(reply)}')
    good, bad, truncated = struct.unpack('>HHH', bytes(reply))
    return good, bad, truncated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--port', required=True, help='serial port of the board')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--demo', action='store_true',
                        help='send one good frame, one bad frame and one truncated frame')
    parser.add_argument('--hex', nargs='+', metavar='WORD',
                        help='send one frame per pair of words, for example 6a5b 8c2d')
    args = parser.parse_args(argv)

    import serial  # pyserial, needed only to talk to the board

    transfers = []
    if args.demo:
        transfers.append(('good frame', make_frame(0x6A5B, 0x8C2D)))
        bad = bytearray(make_frame(0x5F10, 0x4A00))
        bad[2] ^= 0x01
        transfers.append(('bad temperature CRC', bytes(bad)))
        transfers.append(('truncated frame', bytes([0x12, 0x34, 0x56])))
    if args.hex:
        words = [int(w, 16) for w in args.hex]
        if len(words) % 2:
            parser.error('--hex needs an even number of words: temperature, humidity pairs')
        for i in range(0, len(words), 2):
            transfers.append((f'frame {i // 2 + 1}', make_frame(words[i], words[i + 1])))
    if not transfers:
        parser.error('nothing to send: use --demo or --hex')

    with serial.Serial(args.port, args.baud, timeout=5) as link:
        for name, payload in transfers:
            link.write(pack_transfer(payload))
            reply = link.read(6)
            good, bad, truncated = parse_reply(reply)
            print(f'{name:24s} good={good} bad={bad} truncated={truncated}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
