"""Run a divider sweep on the real core/PLL/FIFO assembly, without a cross compiler."""
import random

import cocotb
from cocotb.triggers import Timer
from pll_env import Reference
from rv_reference import i_type, store


@cocotb.test()
async def firmware_sweep(d):
    # x1 = MMIO base, x7 = output RAM; unrolled firmware captures three samples
    # per divider, then copies them out through FIFO reads.
    code=[0x100000b7,0x000043b7]
    for ratio in range(2,9):
        code += [i_type(2,0,ratio|256),store(1,2),i_type(2,0,ratio),store(1,2)]
        code += [i_type(0,0,0)]*12
        code += [store(1,0,8)]*3
        for index in range(3):
            code += [i_type(4,1,8,2,3),store(7,4,(ratio-2)*12+index*4)]
    code += [i_type(3,0,1),0x73]
    ram=bytearray(1<<16)
    ram[:len(code)*4]=b''.join(x.to_bytes(4,'little') for x in code)
    expected=[]
    model=Reference()
    ratio, hold, actual=(2,1,(0,0,0,0,8))
    rng=random.Random(17)
    stores=0
    for cycle in range(3000):
        d.clk.value=0; d.reset.value=int(cycle<2)
        ref=int(rng.random()<0.35)
        d.ref_pulse.value=ref
        await Timer(1,unit='ns')
        pc=int(d.imem_addr.value)
        d.imem_data.value=int.from_bytes(ram[pc:pc+4],'little')
        addr=int(d.mem_addr.value)
        d.mem_rdata.value=int.from_bytes(ram[addr:addr+4],'little') if addr<len(ram)-4 else 0
        await Timer(4,unit='ns')
        if cycle>=2:
            feedback,up,down,locked,control=actual
            assert int(d.capture_sample.value)==ratio<<8|control<<4|locked<<3|down<<2|up<<1|feedback
            if int(d.capture_valid.value): expected.append(int(d.capture_sample.value))
            strobe=int(d.mem_wstrb.value)
            data=int(d.mem_wdata.value)
            if strobe:
                assert addr==0x4000+stores*4
                assert data==expected[stores], 'Firmware/FIFO changed or reordered the PLL sample'
                assert (data>>8)==2+stores//3
                stores+=1
                for i in range(4):
                    if strobe>>i&1: ram[addr+i]=data>>(8*i)&255
        actual=model.step(cycle<2 or hold,ref,ratio)
        # MMIO writes affect the PLL starting on the following edge. The reset
        # sequence is known from firmware; observe the core bus before the edge.
        if cycle<2: ratio,hold=2,1
        elif addr==0x10000000 and int(d.mmio_write.value):
            ratio=int(d.mem_wdata.value)&15
            hold=int(d.mem_wdata.value)>>8&1
        d.clk.value=1
        await Timer(5,unit='ns')
        if int(d.retire_trap.value):
            assert int(d.test_number.value)==1
            assert stores==21 and len(expected)==21
            return
    assert False,'Divider sweep did not complete'
