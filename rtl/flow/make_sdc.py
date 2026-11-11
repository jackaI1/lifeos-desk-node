"""Write the timing constraints for one clock period.

One clock named core_clock on port clk. Inputs and outputs get a budget of 20 %
of the period, so the logic between the ports and the registers gets the rest.
"""
import argparse
from pathlib import Path


def sdc_text(period_ns):
    budget = round(0.2 * period_ns, 4)
    return (
        f'create_clock -name core_clock -period {period_ns} [get_ports clk]\n'
        f'set_input_delay {budget} -clock core_clock '
        '[delete_from_list [all_inputs] [get_ports clk]]\n'
        f'set_output_delay {budget} -clock core_clock [all_outputs]\n'
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('period_ns', type=float)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(sdc_text(args.period_ns))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
