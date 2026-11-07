from can_monitor.thermal import from_rust_run,simulate
from can_monitor.replay import replay


def test_bad_command_cannot_heat_plant_and_next_frame_recovers():
    clean=simulate(steps=4);fault=simulate(steps=4,fault_at=2)
    assert fault[2]['heater']==0 and fault[2]['fault']
    assert fault[2]['temperature']<clean[2]['temperature']
    # Bad CRC cannot advance the counter; following frame reports the gap, then recovers.
    assert fault[3]['fault']
    assert not simulate(steps=5,fault_at=2)[4]['fault']


def test_rust_process_data_uses_same_dbc_decoder(tmp_path):
    source=tmp_path/'run.csv';target=tmp_path/'run.jsonl'
    source.write_text('temperature_mc,heater_percent\n21500,45\n22000,0\n')
    from_rust_run(source,target);result=replay(target)
    assert result['frames'][0]['signals']['Temperature']==21.5
    assert result['frames'][0]['safe']['heater']==45
