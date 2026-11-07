"""Map both real processor versions to Sky130 and compare OpenSTA critical paths."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

LIB_REV='c5310d7ffdd5f8a1eed83089697631548cc08a99'
LIB_PATH='flow/platforms/sky130hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib'


def arrival(report):
    # The slack calculation repeats the arrival as a negative subtraction.
    # Only the positive standalone path row is the measured arrival.
    values=re.findall(r'^\s*([0-9]+\.[0-9]+)\s+data arrival time\s*$', report, re.MULTILINE)
    if len(values)!=1:
        raise ValueError('Expected exactly one constrained maximum-delay path')
    value=float(values[0])
    if value<=0: raise ValueError('Critical path must have a positive delay')
    return value


def run(output=Path('build/timing')):
    output=output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    liberty=output/'sky130.lib'
    with urllib.request.urlopen(f'https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD-flow-scripts/{LIB_REV}/{LIB_PATH}',timeout=60) as response:
        liberty.write_bytes(response.read(25_000_000))
    numbers={}
    for label,fast in [('before',0),('after',1)]:
        netlist=output/f'{label}.v'
        script=output/f'{label}.ys'
        script.write_text(f'''read_verilog -sv rtl/rv32_core.sv
chparam -set FAST_ALU {fast} rv32_core
synth -top rv32_core -noabc
dfflibmap -liberty {liberty}
abc -liberty {liberty}
clean -purge
read_liberty -lib {liberty}
check -assert
stat -liberty {liberty}
write_verilog -noattr -noexpr -simple-lhs {netlist}
''')
        with (output/f'{label}-yosys.log').open('w') as log:
            subprocess.run(['yosys','-s',str(script)],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        sta=output/f'{label}.tcl'
        sta.write_text(f'''read_liberty {liberty}
read_verilog {netlist}
link_design rv32_core
create_clock -name clk -period 100 [get_ports clk]
set_input_delay -clock clk 1 [get_ports {{reset imem_data* dmem_rdata*}}]
set_input_transition 0.1 [get_ports {{reset imem_data* dmem_rdata*}}]
set_output_delay -clock clk 1 [all_outputs]
set_load 0.05 [all_outputs]
set_false_path -from [get_ports reset]
report_checks -path_delay max -group_path_count 1 -digits 4
report_worst_slack -max
exit
''')
        proc=subprocess.run([os.environ.get('OPENSTA','sta'),'-no_splash','-exit',str(sta)],
                            capture_output=True,text=True,timeout=120,check=True)
        report=proc.stdout+proc.stderr
        (output/f'{label}-opensta.txt').write_text(report)
        if re.search(r'(^|\n)Error',report): raise RuntimeError(report[-2000:])
        numbers[label+'_ns']=arrival(report)
    numbers['improvement_percent']=round(100*(numbers['before_ns']-numbers['after_ns'])/numbers['before_ns'],2)
    numbers.update({'library':'Sky130 HD tt 25C 1.80V','library_revision':LIB_REV,
                    'library_sha256':hashlib.sha256(liberty.read_bytes()).hexdigest(),
                    'clock_period_ns':100,'input_delay_ns':1,'output_delay_ns':1,
                    'output_load_pf':0.05,'input_transition_ns':0.1,
                    'parasitics':'cell pins only; no placement or extracted wire delays',
                    'opensta':subprocess.check_output([os.environ.get('OPENSTA','sta'),'-version'],text=True).strip(),
                    'yosys':subprocess.check_output(['yosys','-V'],text=True).strip()})
    (output/'summary.json').write_text(json.dumps(numbers,indent=2)+'\n')
    print(json.dumps(numbers,indent=2))
    if numbers['improvement_percent']<=0:
        raise RuntimeError('Carry-select implementation did not improve the measured critical path')
    return numbers


if __name__=='__main__': run()
