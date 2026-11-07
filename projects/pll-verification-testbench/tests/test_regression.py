from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('bug', [False, True], ids=['correct-design', 'injected-divider-bug'])
def test_pll(tmp_path, bug):
    runner = get_runner('verilator')
    runner.build(sources=[ROOT / 'rtl/pll_control.sv'], hdl_toplevel='pll_control',
                 build_dir=tmp_path / 'build', always=True,
                 parameters={'INJECT_BUG': int(bug)}, build_args=['--assert'])
    kwargs = dict(hdl_toplevel='pll_control', test_module='pll_env',
                  test_dir=tmp_path, build_dir=tmp_path / 'build',
                  results_xml=str(tmp_path / 'results.xml'), extra_env={'PYTHONPATH': str(ROOT / 'tests')})
    if bug:
        with pytest.raises(SystemExit):
            runner.test(**kwargs)
        failure = ET.parse(tmp_path / 'results.xml').find('.//failure')
        assert failure is not None and 'divider/control mismatch' in failure.attrib['message']
    else:
        runner.test(**kwargs)
