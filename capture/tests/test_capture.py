"""End-to-end tests run installed sigrok decoders, Scheme, and the C replay."""
import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

from capture.common import save_sr
from capture.decode import Annotation, analyze, annotations, crc8, csv_samples, decode, main
from capture.generate import RATE, Wave, generate

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='session')
def replay_bin(tmp_path_factory):
    build = tmp_path_factory.mktemp('capture-replay')
    subprocess.run(['make', '-C', str(ROOT / 'replay'), f'BUILD={build}',
                    'CFLAGS=-g -fsanitize=address,undefined -fno-omit-frame-pointer'],
                   check=True, capture_output=True)
    return build / 'desk-replay'


@pytest.fixture
def scenario(tmp_path, replay_bin):
    def run(plan='(scenario (sample 25000 50000))', faults=(), suffix='.sr'):
        compiled = subprocess.run(['guile', '--no-auto-compile', '-L', str(ROOT / 'replay/scheme'),
                                   str(ROOT / 'replay/compile.scm')], input=plan, text=True,
                                  capture_output=True, check=True).stdout
        uart = tmp_path / 'uart.txt'
        replay = subprocess.run([str(replay_bin), '--uart-log', str(uart)], input=compiled,
                                text=True, capture_output=True, check=True)
        samples, manifest = generate(compiled, uart.read_bytes(), faults)
        path = tmp_path / ('capture' + suffix)
        if suffix == '.sr':
            save_sr(samples, path, RATE)
        else:
            with path.open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['SCL', 'SDA', 'TX'])
                writer.writerows((b & 1, (b >> 1) & 1, (b >> 2) & 1) for b in samples)
        return path, uart.read_bytes(), manifest, json.loads(replay.stdout)
    return run


def codes(report):
    return [f['code'] for f in report['findings']]


@pytest.mark.parametrize('suffix', ['.sr', '.csv'])
def test_clean_roundtrip_real_decoders(scenario, suffix):
    path, uart, manifest, replay = scenario(suffix=suffix)
    report = decode(path, samplerate=RATE)
    assert report['ok'], report['findings']
    assert report['sensor_readings'] == [dict(sample=40770, raw='6666938000a2', crc_ok=True,
                                             temperature_c=25.0, humidity_percent=50.001)]
    assert bytes.fromhex(report['uart']['hex']) == uart
    assert report['uart']['byte_count'] == manifest['uart_bytes']
    assert 'temp_mc=25000 rh_mpermil=50001 queued=1' in report['uart']['text']
    assert replay['samples'] == 1
    assert len(report['normal_read_end_nacks']) == 1
    assert [b['value'] for b in report['i2c_transactions'][0]['bytes']] == [0x44, 0x24, 0]


@pytest.mark.parametrize('fault,expected', [('nack', ['unexpected_nack']),
    ('missing-ack', ['incomplete_transaction', 'missing_ack']),
    ('humidity-crc', ['bad_crc']), ('uart-framing', ['uart_framing'])])
@pytest.mark.parametrize('suffix', ['.sr', '.csv'])
def test_each_injected_fault(scenario, fault, expected, suffix):
    path, _, _, _ = scenario(faults=[fault], suffix=suffix)
    report = decode(path, samplerate=RATE)
    assert not report['ok']
    assert codes(report) == expected
    assert all(f['sample'] > 0 for f in report['findings'])
    if fault == 'humidity-crc':
        assert 'humidity CRC' in report['findings'][0]['message']
        assert report['sensor_readings'][0]['temperature_c'] is None


def test_scheme_fault_is_detected_by_capture_and_production_decoder(scenario):
    path, _, _, replay = scenario('(scenario (fault 25000 50000))')
    report = decode(path)
    assert replay['faults'] == 1
    assert codes(report) == ['bad_crc']
    assert 'temperature CRC is 0x92; expected 0x93' in report['findings'][0]['message']
    assert 'sample=unavailable' in report['uart']['text']


def test_multiple_cycles_upload_and_combined_damage(scenario):
    path, uart, _, replay = scenario('(scenario (sample 25000 50000) (upload) (fault 0 0) (sample -45000 100000))',
                                   faults=['nack', 'missing-ack', 'humidity-crc', 'uart-framing'])
    report = decode(path)
    assert sorted(codes(report)) == sorted(['unexpected_nack', 'bad_crc', 'uart_framing',
                                            'bad_crc', 'missing_ack', 'incomplete_transaction'])
    assert len(report['sensor_readings']) == 3
    assert report['sensor_readings'][-1]['temperature_c'] == -45
    assert report['sensor_readings'][-1]['humidity_percent'] == 100
    assert replay['samples'] == 2 and replay['uploaded'] == 1
    assert bytes.fromhex(report['uart']['hex']) == uart


@pytest.mark.parametrize('protocols', ['i2c', 'uart'])
def test_individual_protocols(scenario, protocols):
    path, _, _, _ = scenario()
    assert decode(path, protocols=protocols)['ok']


def test_real_sr_channel_remapping(scenario, tmp_path):
    from capture.common import sigrok
    path, _, _, _ = scenario()
    renamed = tmp_path / 'renamed.sr'
    sigrok(['-i', path, '-C', 'SCL=clock,SDA=data,TX=serial', '-o', renamed, '-O', 'srzip'])
    assert decode(renamed, scl='clock', sda='data', tx='serial')['ok']


@pytest.mark.parametrize('protocols,header,channels', [
    ('i2c', 'clock,data', ['--scl', 'clock', '--sda', 'data']),
    ('uart', 'serial', ['--tx', 'serial'])])
def test_csv_only_connected_channels(scenario, tmp_path, protocols, header, channels):
    path, _, _, _ = scenario(suffix='.csv')
    rows = list(csv.reader(path.open()))
    path.write_text(header + '\n' + '\n'.join(','.join(row[:2] if protocols == 'i2c' else row[2:])
                                                 for row in rows[1:]) + '\n')
    assert main([str(path), '--samplerate', str(RATE), '--protocols', protocols,
                 '--report', str(tmp_path / 'single.json'), *channels]) == 0


def test_missing_final_nack_is_not_treated_as_normal(scenario, tmp_path):
    path, uart, _, _ = scenario()
    samples, _ = generate('DESK_REPLAY_V1\nS 6666938000a2\n', uart)
    # Master ACKs the last byte instead of releasing SDA for the final NACK.
    samples[42160:42200] = bytes(level & ~2 for level in samples[42160:42200])
    save_sr(samples, tmp_path / 'ack.sr', RATE)
    assert codes(decode(tmp_path / 'ack.sr')) == ['missing_final_nack']


def test_csv_channel_mapping_and_uniform_time(tmp_path):
    path = tmp_path / 'custom.csv'
    path.write_text('Time [s],clock,data,serial\n0,1,0,1\n0.0000005,0,1,0\n')
    assert csv_samples(path, ('clock', 'data', 'serial'), RATE) == bytes([5, 2])
    path.write_text('time,SCL,SDA,TX\n0,1,1,1\n0.01,1,1,1\n')
    with pytest.raises(ValueError, match='uniformly'):
        csv_samples(path, ('SCL', 'SDA', 'TX'), RATE)


@pytest.mark.parametrize('text,rate', [('', RATE), ('SCL,SDA,TX\n', RATE),
    ('SCL,SCL,TX\n1,0,1\n', RATE), ('SCL,SDA,TX\n1,2,1\n', RATE),
    ('SCL,SDA,TX\n1,1\n', RATE), ('SCL,SDA,TX\n1,1,1\n', None),
    ('time,SCL,SDA,TX\nnan,1,1,1\n', RATE)])
def test_bad_csv_rejected(tmp_path, text, rate):
    path = tmp_path / 'bad.csv'
    path.write_text(text)
    with pytest.raises(ValueError):
        csv_samples(path, ('SCL', 'SDA', 'TX'), rate)


def test_crc_known_vectors_and_annotation_contract():
    assert crc8(bytes.fromhex('6666')) == 0x93
    assert crc8(bytes.fromhex('8000')) == 0xa2
    with pytest.raises(ValueError, match='unrecognized'):
        annotations('changed output syntax', 'i2c')


def test_repeated_start_short_read_and_early_nack():
    events = [Annotation(i, i, text) for i, text in enumerate([
        'Start', 'Address write: 44', 'ACK', 'Data write: 24', 'ACK',
        'Start repeat', 'Address read: 44', 'ACK', 'Data read: 66', 'NACK', 'Stop'])]
    report = analyze(events, [], 'i2c')
    assert codes(report) == ['sensor_length', 'unexpected_nack']
    assert all(t['complete'] for t in report['i2c_transactions'])


def test_idle_capture_is_not_a_pass(tmp_path):
    path = tmp_path / 'idle.sr'
    save_sr(bytes([7]) * 1000, path, RATE)
    assert codes(decode(path)) == ['no_sensor_traffic', 'no_uart_traffic']


def test_cli_exit_codes_and_report(scenario, tmp_path):
    path, _, _, _ = scenario()
    output = tmp_path / 'report.json'
    assert main([str(path), '--report', str(output)]) == 0
    assert json.loads(output.read_text())['ok']
    path, _, _, _ = scenario(faults=['nack'])
    assert main([str(path), '--report', str(output)]) == 1
    assert not json.loads(output.read_text())['ok']
    assert main([str(tmp_path / 'missing.sr')]) == 2
    assert main([str(path), '--scl', 'nonexistent']) == 2


def test_generator_cli_and_manifest(scenario, tmp_path):
    path, _, _, _ = scenario()
    # Fixture writes UART log with real firmware text; exercise public generator CLI.
    wire = tmp_path / 'plan.wire'
    wire.write_text('DESK_REPLAY_V1\nS 6666938000a2\n')
    output = tmp_path / 'generated.sr'
    result = subprocess.run([sys.executable, '-m', 'capture.generate', str(wire),
                             '--uart-log', str(tmp_path / 'uart.txt'), '--output', str(output),
                             '--fault', 'uart-framing'], cwd=ROOT, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert codes(decode(output)) == ['uart_framing']
    assert json.loads(output.with_suffix('.sr.json').read_text())['synthetic'] is True


@pytest.mark.parametrize('wire,log', [('bad', b''), ('DESK_REPLAY_V1\nS nothex\n', b'desk x\r\n'),
    ('DESK_REPLAY_V1\nU\n', b'wrong\n')])
def test_generator_rejects_invalid_inputs(wire, log):
    with pytest.raises(ValueError):
        generate(wire, log)


def test_waveform_size_limit():
    from capture.common import MAX_SAMPLES
    wave = Wave()
    with pytest.raises(ValueError, match='8 million'):
        wave.hold(MAX_SAMPLES + 1)


def test_replay_uart_output_errors_and_invalid_input(tmp_path, replay_bin):
    result = subprocess.run([str(replay_bin), '--uart-log', str(tmp_path)],
                            input='DESK_REPLAY_V1\nU\n', text=True, capture_output=True)
    assert result.returncode != 0
    log = tmp_path / 'should-not-exist.txt'
    result = subprocess.run([str(replay_bin), '--uart-log', str(log)],
                            input='DESK_REPLAY_V1\nU\ninvalid\n', text=True, capture_output=True)
    assert result.returncode != 0
    assert not log.exists()
