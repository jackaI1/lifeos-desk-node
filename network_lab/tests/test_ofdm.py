import math
import os
import numpy as np
import pytest
from network_lab.ofdm import channel,evm,octave_reference,receive,transmit


def symbols():
    rng=np.random.default_rng(42);return ((2*rng.integers(0,2,256)-1)+1j*(2*rng.integers(0,2,256)-1))/math.sqrt(2)


def test_numpy_roundtrip():
    data=symbols();assert evm(receive(transmit(data),frames=4),data)<1e-12


@pytest.mark.skipif(os.getenv('DESK_GNURADIO')!='1',reason='Linux CI installs GNU Radio and Octave')
@pytest.mark.parametrize('doppler,delay',[(0,0),(1500,12),(-2000,40)])
def test_gnuradio_doppler_delay_and_octave(tmp_path,doppler,delay):
    data=symbols();samples=transmit(data);impaired=channel(samples,doppler_hz=doppler,delay=delay)
    corrected=receive(impaired,frames=4,doppler_hz=doppler,delay=delay)
    assert evm(corrected,data)<.01
    reference=octave_reference(samples,tmp_path,doppler_hz=doppler,delay=delay)
    assert evm(reference,data)<1e-12
    if doppler:assert evm(receive(impaired,frames=4,delay=delay),data)>.5
