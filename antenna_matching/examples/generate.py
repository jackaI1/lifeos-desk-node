"""Reproducible SYNTHETIC 25-ohm series-RLC antenna stand-in, not VNA data."""
from pathlib import Path
import numpy as np


def generate(path):
    f = np.linspace(2.3e9,2.6e9,61)
    w = 2*np.pi*f
    z = 25 + 1j*(w*5e-9 - 1/(w*.7e-12))
    s = (z-50)/(z+50)
    with Path(path).open('w') as out:
        out.write('! SYNTHETIC series RLC: R=25ohm L=5nH C=0.7pF. NOT measured.\n# Hz S RI R 50\n')
        for hz,gamma in zip(f,s):
            out.write(f'{hz:.0f} {gamma.real:.12g} {gamma.imag:.12g}\n')


if __name__ == '__main__':
    generate(Path(__file__).with_name('synthetic-antenna.s1p'))
