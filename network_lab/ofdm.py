"""Small QPSK OFDM lab, using a real GNU Radio streaming channel on Linux."""
import math
from pathlib import Path
import subprocess
import numpy as np


def transmit(symbols,cp=16):
    # 64 carriers, QPSK, a cyclic prefix repeats the tail to tolerate delay.
    frames=np.fft.ifft(np.asarray(symbols).reshape(-1,64),axis=1)*8
    return np.concatenate([frames[:,-cp:],frames],axis=1).reshape(-1)


def receive(samples,*,frames,doppler_hz=0,sample_rate=64000,delay=0,cp=16):
    clean=np.asarray(samples)[delay:delay+frames*(64+cp)]
    corrected=clean*np.exp(-2j*np.pi*doppler_hz*np.arange(len(clean))/sample_rate)
    blocks=corrected.reshape(frames,64+cp)[:,cp:]
    return (np.fft.fft(blocks,axis=1)/8).reshape(-1)


def channel(samples,*,doppler_hz=1500,sample_rate=64000,delay=12,noise=.001):
    from gnuradio import blocks,channels,gr
    graph=gr.top_block()
    source=blocks.vector_source_c(list(samples),False)
    model=channels.channel_model(noise_voltage=noise,frequency_offset=doppler_hz/sample_rate,taps=[1+0j],noise_seed=42,block_tags=False)
    latency=blocks.delay(gr.sizeof_gr_complex,delay)
    # Feed enough zeros to flush the delayed tail; vector sources otherwise end early.
    source=blocks.vector_source_c(list(samples)+[0j]*delay,False)
    sink=blocks.vector_sink_c();graph.connect(source,model,latency,sink)
    graph.run()
    return np.asarray(sink.data())


def evm(actual,expected):return float(np.sqrt(np.mean(np.abs(actual-expected)**2)/np.mean(np.abs(expected)**2)))


def octave_reference(samples,output,*,doppler_hz=1500,sample_rate=64000,delay=12):
    output=Path(output).resolve();output.mkdir(exist_ok=True,parents=True)
    np.savetxt(output/'tx.csv',np.column_stack([samples.real,samples.imag]),delimiter=',')
    function=Path(__file__).with_name('ofdm_reference.m').resolve()
    expression=f"addpath('{function.parent}'); ofdm_reference('{output}',{doppler_hz},{sample_rate},{delay});"
    subprocess.run(['octave','--no-gui','--quiet','--eval',expression],check=True,capture_output=True,timeout=30)
    data=np.loadtxt(output/'rx.csv',delimiter=',');return data[:,0]+1j*data[:,1]


def main():
    rng=np.random.default_rng(42);symbols=((rng.integers(0,2,256)*2-1)+1j*(rng.integers(0,2,256)*2-1))/math.sqrt(2)
    samples=transmit(symbols);decoded=receive(channel(samples),frames=4,doppler_hz=1500,delay=12)
    print(f'GNU Radio 64-carrier QPSK, 1500 Hz Doppler, 12 samples delay: EVM={evm(decoded,symbols):.6f}')


if __name__=='__main__':main()
