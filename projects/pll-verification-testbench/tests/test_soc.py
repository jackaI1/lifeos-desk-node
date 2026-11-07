from pathlib import Path
from cocotb_tools.runner import get_runner

ROOT=Path(__file__).resolve().parents[1]


def test_firmware_divider_sweep(tmp_path):
    runner=get_runner('verilator')
    runner.build(sources=[ROOT/'rtl'/name for name in ['rv32_core.sv','pll_control.sv','sample_fifo.sv','pll_soc.sv']],
                 hdl_toplevel='pll_soc',build_dir=tmp_path/'build',build_args=['--assert','-Wno-fatal'])
    runner.test(hdl_toplevel='pll_soc',test_module='soc_env',test_dir=tmp_path,
                results_xml=str(tmp_path/'result.xml'),extra_env={'PYTHONPATH':str(ROOT/'tests')})
