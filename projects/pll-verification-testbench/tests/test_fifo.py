from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('depth', [1, 3, 8])
def test_fifo(tmp_path, depth):
    runner = get_runner('verilator')
    runner.build(sources=[ROOT / 'rtl/sample_fifo.sv'], hdl_toplevel='sample_fifo',
                 build_dir=tmp_path / 'build', parameters={'DEPTH': depth},
                 build_args=['--assert', '-Wno-fatal'])
    for seed in [17, 409, 20261106]:
        runner.test(hdl_toplevel='sample_fifo', test_module='fifo_env',
                    test_dir=tmp_path, results_xml=str(tmp_path / f'{seed}.xml'),
                    extra_env={'PYTHONPATH': str(ROOT / 'tests'), 'FIFO_DEPTH': str(depth),
                               'TEST_SEED': str(seed)})
