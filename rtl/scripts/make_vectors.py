"""Write checksum test vectors from the replay tool's wire recordings.

Each sample line in a wire file is one six-byte frame: two words, each followed
by its CRC byte. The output has one line per word: frame index, word index, the
two data bytes, the checksum byte and the reference verdict (1 = checksum good).
Random words with single-bit corruption are appended, labelled by the reference.
"""
import argparse
import random
import sys
from pathlib import Path

import sht31_ref


def word_lines(frames, rng=None, random_words=0):
    rows = []
    for index, frame in enumerate(frames):
        for word in range(2):
            data = frame[3 * word:3 * word + 2]
            check = frame[3 * word + 2]
            ok = sht31_ref.crc8(data) == check
            rows.append((index, word, data, check, ok))
    if rng is not None:
        for index in range(random_words):
            data = bytes(rng.randrange(256) for _ in range(2))
            check = sht31_ref.crc8(data)
            if rng.random() < 0.5:
                check ^= 1 << rng.randrange(8)     # one flipped checksum bit
            ok = sht31_ref.crc8(data) == check
            rows.append((len(frames) + index, 0, data, check, ok))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wires', nargs='+', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--random', type=int, default=2000)
    args = parser.parse_args(argv)
    frames = []
    for path in args.wires:
        frames.extend(sht31_ref.wire_frames(path))
    rows = word_lines(frames, random.Random(42), args.random)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('w') as stream:
        for frame_index, word, data, check, ok in rows:
            stream.write(f'{data.hex()} {check:02x} {int(ok)} {frame_index} {word}\n')
    print(f'wrote {len(rows)} word vectors from {len(frames)} frames to {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
