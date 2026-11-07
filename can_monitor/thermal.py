"""Apply checked CAN commands to the existing room-control simulation."""
import csv
import json
import uuid
import can
from automation.control import Reading,Thermostat
from .monitor import Monitor,make_frame
from .replay import record


def simulate(*,steps=50,fault_at=None):
    monitor=Monitor(timeout=.3);controller=Thermostat();temperature=20.;rows=[]
    options=dict(interface='virtual',channel='thermal-'+uuid.uuid4().hex,ignore_config=True)
    with can.Bus(**options) as tx,can.Bus(**options) as rx:
        for i in range(steps):
            now=1+i*.1
            controller.update(Reading(temperature,50,now),now)
            command=make_frame(temperature,i%256,setpoint=controller.setpoint,heater=60 if controller.heat else 0,fan=40 if controller.fan else 0)
            if i==fault_at:command.data[0]^=1
            tx.send(command);received=rx.recv(1)
            if received is None:raise TimeoutError('CAN command not delivered')
            result=monitor.process(received,now);output=result['safe']
            temperature+=(output['heater']*.001-(temperature-20)*.01)
            rows.append(dict(time=now,temperature=temperature,**output,errors=result['errors']))
    return rows


def from_rust_run(source,target):
    """Turn the Rust supervisor's actual process log into a DBC replay recording."""
    with open(source,newline='') as stream,open(target,'w') as out:
        for i,row in enumerate(csv.DictReader(stream)):
            frame=make_frame(int(row['temperature_mc'])/1000,i%256,heater=int(row['heater_percent']))
            out.write(json.dumps(record(frame,i*.01))+'\n')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rust-csv');p.add_argument('--output',default='/tmp/rust-can.jsonl');a=p.parse_args()
    if a.rust_csv:from_rust_run(a.rust_csv,a.output)
    else:print(json.dumps(simulate(fault_at=10),indent=2))
