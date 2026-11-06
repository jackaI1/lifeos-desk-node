"""SCPI-driven sweeps with raw CSV traces, reproducibility metadata and plots."""
import csv
import gzip
import json
import platform
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import numpy as np

from .analysis import analyze_eye, analyze_spectrum, sensitivity
from .instruments import Attenuator, Bert, Dca, Osa, SimResourceManager
from .model import LinkConfig


def _write_csv(path, rows):
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def _plot(path, ber_rows, eye_capture, spectrum, config):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), layout='constrained')
    try:
        power = [r['power_dbm'] for r in ber_rows]
        # Zero counts get an upper-bound marker, never an invented measured BER.
        observed = [r['ber'] if r['errors'] else np.nan for r in ber_rows]
        axes[0].semilogy(power, observed, 'o-', label='Observed BER (nonzero)')
        axes[0].semilogy(power, [r['ber_upper_95'] for r in ber_rows], 'v--',
                         label='95% upper bound')
        axes[0].set(xlabel='Received power (dBm)', ylabel='Bit errors / tested bits',
                    title='Receiver sensitivity curve')
        axes[0].legend(fontsize=8)
        axes[0].grid(True, alpha=.25)
        sps = config.samples_per_bit
        # Two-UI windows centered on the bit being measured, spanning neighbor halves.
        samples = eye_capture.samples_mw
        starts = np.arange(1, min(config.n_bits - 1, 401)) * sps - sps // 2
        time = np.arange(2*sps) / sps - .5
        for start in starts:
            axes[1].plot(time, samples[start:start+2*sps], color='#126f85', alpha=.06, lw=.6)
        axes[1].axvline(.5, color='black', ls=':', lw=.8)
        axes[1].set(xlabel='Time (bit periods, UI)', ylabel='Detected power (mW)',
                    title=f'Eye at {ber_rows[-1]["power_dbm"]:g} dBm')
        axes[2].plot(*spectrum, color='#9a441d')
        axes[2].set(xlabel='Wavelength (nm)', ylabel='Spectral sample (dBm)',
                    title='Separate simulated laser spectrum')
        fig.suptitle('SIMULATED DATA ONLY | No physical optical equipment used')
        fig.savefig(path, dpi=140)
    finally:
        plt.close(fig)


def run_sweep(output, config: LinkConfig, powers, target_ber: float = .001) -> dict:
    powers = [float(p) for p in powers]
    if (not powers or not np.isfinite(powers).all() or len(set(powers)) != len(powers)
            or not all(-80 <= p <= 20 for p in powers)):
        raise ValueError('powers must be unique, finite and -80..20 dBm')
    if not np.isfinite(target_ber) or not 0 < target_ber < 1:
        raise ValueError('target BER must be between zero and one')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    metadata = dict(simulated=True, physical_equipment_used=False, status='running',
                    config=asdict(config), powers_dbm=sorted(powers), target_ber=target_ber,
                    python=platform.python_version(),
                    versions={p: version(p) for p in ['numpy', 'scipy', 'matplotlib',
                                                       'optical-link-test-analysis']},
                    waveform_layout='one row per bit: reference, decision, then s0..sN in mW',
                    sample_time_ps='(bit_index * samples_per_bit + sample_index) * '
                                   '1000 / (bit_rate_gbps * samples_per_bit)')
    metadata_path = output / 'metadata.json'
    def save_metadata():
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
    save_metadata()
    ber_rows, eye_rows, spectrum_rows = [], [], []
    manager = SimResourceManager(config)
    try:
        with manager:
            att = Attenuator(manager.open_resource('SIM::ATT'))
            bert = Bert(manager.open_resource('SIM::BERT'))
            dca = Dca(manager.open_resource('SIM::DCA'))
            osa = Osa(manager.open_resource('SIM::OSA'))
            for i, power in enumerate(sorted(powers)):
                att.set_power(power)
                bert_result = bert.measure()
                capture = dca.capture()
                eye = analyze_eye(capture.samples_mw, capture.bits, config.samples_per_bit)
                eye['eye_width_ps'] = eye['eye_width_ui'] * 1000 / config.bit_rate_gbps
                wavelength, spectral_power = osa.trace()
                spectral = analyze_spectrum(wavelength, spectral_power)
                identity = dict(point=i, power_dbm=power, simulated=True)
                ber_rows.append(dict(**identity, **bert_result))
                eye_rows.append(dict(**identity, **eye))
                spectrum_rows.append(dict(**identity, **spectral))
                # Save complete traces, not just the plotted subset. Compress losslessly.
                matrix = np.column_stack([capture.bits, capture.decisions,
                    capture.samples_mw.reshape(-1, config.samples_per_bit)])
                header = 'reference_bit,decision,' + ','.join(
                    f's{j}_mw' for j in range(config.samples_per_bit))
                with gzip.open(output / f'point_{i:03d}_waveform.csv.gz', 'wt') as stream:
                    np.savetxt(stream, matrix, delimiter=',', fmt='%.10g',
                               header=header, comments='')
                np.savetxt(output / f'point_{i:03d}_spectrum.csv',
                    np.column_stack([wavelength, spectral_power]), delimiter=',',
                    fmt='%.10g', header='wavelength_nm,power_dbm', comments='')
                # Flush summary tables after each completed point for partial-run recovery.
                _write_csv(output / 'ber.csv', ber_rows)
                _write_csv(output / 'eye.csv', eye_rows)
                _write_csv(output / 'spectrum_metrics.csv', spectrum_rows)
                del matrix
            result = sensitivity(ber_rows, target_ber)
            _write_csv(output / 'sensitivity.csv', [dict(simulated=True, **result)])
            _plot(output / 'summary.png', ber_rows, capture,
                  (wavelength, spectral_power), config)
        metadata['status'] = 'complete'
        return result
    except BaseException:
        metadata['status'] = 'failed'
        raise
    finally:
        manager.close()
        try:
            if manager.bench.log:
                _write_csv(output / 'commands.csv', manager.bench.log)
        except BaseException:
            metadata['status'] = 'failed'
            raise
        finally:
            save_metadata()
