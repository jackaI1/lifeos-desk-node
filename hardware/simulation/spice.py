"""Run ngspice on values read back from KiCad's exported native netlist."""
import argparse
import csv
import json
import math
from pathlib import Path
import random
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def exported_values():
    with tempfile.TemporaryDirectory(prefix='desk-netlist-') as folder:
        path=Path(folder)/'netlist.xml'
        subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(path),str(ROOT/'hardware/simulation/light-front-end.kicad_sch')],check=True,capture_output=True)
        tree=ET.parse(path)
    values={c.attrib['ref']:c.findtext('value') for c in tree.findall('./components/comp')}
    nets={}
    for net in tree.findall('./nets/net'):
        for node in net.findall('node'):nets[(node.attrib['ref'],node.attrib['pin'])]=net.attrib['name']
    assert nets[('R3','1')]==nets[('U2','1')]==nets[('C3','1')]
    assert nets[('R3','2')]==nets[('U2','4')]==nets[('D1','1')]
    assert values['R3']=='100k' and values['C3']=='100pF'
    return 100000.,100e-12


def run_tia(folder,*,rf=100000.,cf=100e-12,ripple=False):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    # Generic finite-bandwidth, rail-limited amplifier model. Not a vendor model.
    net=f'''Desk photodiode current amplifier
.param RF={rf} CF={cf}
Vinput vin 0 SIN(5 .05 1000)
Breg vcc 0 V=3.3+(V(vin)-5)*.001
Rtop vcc ref 100k
Rbottom ref 0 100k
Cref ref 0 1n
Iphoto sum 0 DC 1u AC 1 PULSE(0 1u 100u 1n 1n 1m 2m)
Rfeedback out sum {{RF}}
Cfeedback out sum {{CF}}
Cdiode sum 0 70p
Eerror drive 0 ref sum 100000
Rdominant drive pole 1k
Cdominant pole 0 15.915494u
Boutput out 0 V=min(max(V(ref)+V(pole),.05),V(vcc)-.05)
.control
set wr_singlescale
set wr_vecnames
op
print v(out) v(ref)
dc Iphoto 0 10u .1u
wrdata dc.dat v(out) v(ref)
ac dec 40 10 1Meg
wrdata ac.dat v(out)
tran 1u 5m
wrdata transient.dat v(out) v(ref) v(vcc)
quit
.endc
.end
'''
    if ripple:net=net.replace('DC 1u AC 1 PULSE(0 1u 100u 1n 1n 1m 2m)','DC 1u AC 1')
    (folder/'model.cir').write_text(net)
    result=subprocess.run(['ngspice','-b','model.cir'],cwd=folder,capture_output=True,text=True,timeout=20)
    (folder/'ngspice.log').write_text(result.stdout+result.stderr)
    if result.returncode or not (folder/'dc.dat').exists():raise RuntimeError((result.stdout+result.stderr)[-2000:])
    dc=np.loadtxt(folder/'dc.dat',skiprows=1);ac=np.loadtxt(folder/'ac.dat',skiprows=1);tr=np.loadtxt(folder/'transient.dat',skiprows=1)
    gain=(dc[-1,1]-dc[0,1])/(dc[-1,0]-dc[0,0])
    magnitude=np.hypot(ac[:,1],ac[:,2]);low=magnitude[0];index=np.where(magnitude<=low/math.sqrt(2))[0]
    bandwidth=float(ac[index[0],0]) if len(index) else None
    return dict(gain_ohm=float(gain),bandwidth_hz=bandwidth,step_final_v=float(tr[np.abs(tr[:,0]-.0009).argmin(),1]),
                ripple_vpp=float(np.ptp(tr[tr[:,0]>.003,1])),dc=dc,ac=ac,transient=tr)


def run_leak(folder, supply=3.3):
    """Independent SPICE nodal solve; no ideal switch hides the analog threshold."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    net=f'''Leak probe resistance sweep, ideal open-collector decision model
Vcc vcc 0 {supply}
Rpull vcc sense 1Meg
Rprobe sense 0 1Meg
Rtop vcc ref 100k
Rbottom ref 0 100k
* At onset of wet, output is pulled high; test actual feedback resistor.
Rfeedback vcc sense 10Meg
.control
set wr_singlescale
set wr_vecnames
dc Rprobe 100k 2Meg 10k
wrdata leak.dat v(sense) v(ref)
quit
.endc
.end
'''
    (folder/'leak.cir').write_text(net)
    result=subprocess.run(['ngspice','-b','leak.cir'],cwd=folder,capture_output=True,text=True,timeout=10)
    if result.returncode:raise RuntimeError(result.stderr[-2000:])
    rows=np.loadtxt(folder/'leak.dat',skiprows=1)
    crossing=rows[np.abs(rows[:,1]-rows[:,2]).argmin(),0]
    return float(crossing)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',default='hardware/simulation/build');a=p.parse_args();out=Path(a.output)
    rf,cf=exported_values();base=run_tia(out/'nominal',rf=rf,cf=cf);rng=random.Random(42)
    sweep=[]
    for i in range(16):
        r=rf*rng.uniform(.99,1.01);c=cf*rng.uniform(.95,1.05);x=run_tia(out/f'tolerance-{i}',rf=r,cf=c)
        sweep.append(dict(rf=r,cf=c,gain_ohm=x['gain_ohm'],bandwidth_hz=x['bandwidth_hz']))
    report={k:v for k,v in base.items() if k not in ('dc','ac','transient')}
    report.update(hand_gain_ohm=rf,hand_bandwidth_hz=1/(2*math.pi*rf*cf),tolerances=sweep,
                  ripple=run_tia(out/'ripple',ripple=True)['ripple_vpp'],leak_threshold_ohm=run_leak(out/'leak'))
    out.mkdir(exist_ok=True,parents=True);(out/'results.json').write_text(json.dumps(report,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(12,3.4));axes[0].plot(base['dc'][:,0]*1e6,base['dc'][:,1]);axes[0].set(xlabel='Photocurrent (uA)',ylabel='ADC voltage (V)')
    axes[1].semilogx(base['ac'][:,0],20*np.log10(np.hypot(base['ac'][:,1],base['ac'][:,2])));axes[1].set(xlabel='Frequency (Hz)',ylabel='Gain (dB ohm)')
    axes[2].plot(base['transient'][:,0]*1000,base['transient'][:,1]);axes[2].set(xlabel='Time (ms)',ylabel='ADC voltage (V)')
    fig.tight_layout();fig.savefig(out/'comparison.png',dpi=150);plt.close(fig)
    print(json.dumps({k:v for k,v in report.items() if k!='tolerances'},indent=2))


if __name__=='__main__':main()
