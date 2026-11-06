import json
import subprocess
import sys
from dataclasses import replace

import pytest
from power_budget.model import Assumptions, compare, sleep_seconds


def test_charge_integral_and_runtime():
    a = Assumptions()
    r = compare(a, 300)
    b = r['boards']
    assert r['cycle_s'] == 310
    assert b['B']['parts_ma']['ESP32 awake'] == pytest.approx(1120 / 310)
    assert b['B']['parts_ma']['ESP32 deep sleep (RTC retained)'] == pytest.approx(3 / 310)
    assert b['A']['average_ma'] - b['B']['average_ma'] == pytest.approx(5.245)
    assert b['B']['runtime_hours'] * b['B']['average_ma'] == pytest.approx(300)
    assert b['A']['runtime_hours'] * b['A']['input_power_mw'] == pytest.approx(3.7 * 500 * .85)
    for board in b.values():
        assert sum(board['share_percent'].values()) == pytest.approx(100)


def test_schedule_is_after_work_and_reads_firmware(tmp_path):
    assert sleep_seconds() == 300
    config = tmp_path / 'sdkconfig'
    config.write_text('CONFIG_DESK_UPDATE_SECONDS=600\nCONFIG_DESK_WIFI_PASSWORD="do not print"\n')
    assert sleep_seconds(config) == 600
    assert compare(sleep_s=sleep_seconds(config))['cycle_s'] == 610
    config.write_text('CONFIG_DESK_UPDATE_SECONDS=0')
    with pytest.raises(ValueError):
        sleep_seconds(config)


def test_sensitivity():
    baseline = compare()['boards']['B']
    longer = compare(replace(Assumptions(), awake_s=92))['boards']['B']
    assert longer['average_ma'] > baseline['average_ma']
    assert longer['runtime_hours'] < baseline['runtime_hours']
    assert compare(replace(Assumptions(), capacity_mah=1000))['boards']['B']['runtime_hours'] == pytest.approx(2*baseline['runtime_hours'])
    assert compare(replace(Assumptions(), display_ma=15))['boards']['B']['average_ma'] - baseline['average_ma'] == pytest.approx(12)


@pytest.mark.parametrize('field,value', [('awake_s', -.1), ('awake_ma',0), ('display_ma',float('nan')), ('led_vf',4), ('capacity_mah',0), ('usable_fraction',1.1), ('usb_efficiency',0), ('leakage_ma',-1)])
def test_bad_assumptions(field,value):
    with pytest.raises(ValueError):
        compare(replace(Assumptions(), **{field:value}))


def test_cli_machine_report():
    r = subprocess.run([sys.executable,'-m','power_budget.compare','--json'], capture_output=True,text=True,check=True)
    assert json.loads(r.stdout)['boards']['B']['average_ma'] > 0
