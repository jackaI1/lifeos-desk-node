"""Small sequential RV32I oracle, independent of pipeline implementation."""
import random

MASK = 0xffffffff


def signed(value, bits=32):
    return (value & ((1 << (bits-1))-1)) - (value & (1 << (bits-1)))


def i_type(rd, rs1, imm, f3=0, op=0x13):
    return ((imm & 4095) << 20) | rs1 << 15 | f3 << 12 | rd << 7 | op


def store(rs1, rs2, imm=0, f3=2):
    return (imm & 0xfe0) << 20 | rs2 << 20 | rs1 << 15 | f3 << 12 | (imm & 31) << 7 | 0x23


def program(seed):
    rng = random.Random(seed)
    code = [0x000040b7]  # lui x1,4: test data at 0x4000
    code += [i_type(2, 0, 7), store(1, 2), i_type(4, 1, 0, 2, 3),
             4 << 20 | 4 << 15 | 5 << 7 | 0x33,
             5 << 20 | 5 << 15 | 4 << 8 | 0x63,  # beq x5,x5,+8
             store(1, 0), i_type(6, 1, 0, 2, 3)]
    for _ in range(300):
        rd, a, b = rng.choice([0]+list(range(2, 31))), rng.randrange(2, 31), rng.randrange(2, 31)
        kind, f3 = rng.randrange(6), rng.randrange(8)
        if kind == 0:
            code.append(i_type(rd, a, rng.randrange(-2048, 2048), rng.choice([0,2,3,4,6,7])))
        elif kind == 1:
            upper = rng.choice([0, 0x20]) if f3 in [0,5] else 0
            code.append(upper << 25 | b << 20 | a << 15 | f3 << 12 | rd << 7 | 0x33)
        elif kind == 2:
            shift = rng.randrange(32) | (rng.choice([0,0x400]) if f3 % 2 else 0)
            code.append(i_type(rd, a, shift, 5 if f3 % 2 else 1))
        elif kind == 3:
            offset=rng.randrange(16)
            code += [store(1, a, offset, rng.randrange(3)),
                     i_type(rd, 1, offset, rng.choice([0,1,2,4,5]), 3), i_type(b, rd, 1)]
        elif kind == 4:
            # Forward-only conditional branch makes termination independent of data.
            code += [b << 20 | a << 15 | rng.choice([0,1,4,5,6,7]) << 12 | 4 << 8 | 0x63,
                     i_type(rd, a, 1)]
        else:
            code += [8 << 20 | rd << 7 | 0x6f, i_type(rd, 0, -1)]
    code += [i_type(3,0,1), 0x73]
    return b''.join(x.to_bytes(4, 'little') for x in code)


def reference(image):
    mem = bytearray(image) + bytearray((1<<20)-len(image))
    regs = [0]*32
    pc = 0
    for _ in range(20000):
        insn = int.from_bytes(mem[pc:pc+4], 'little')
        op, rd, f3 = insn & 127, insn >> 7 & 31, insn >> 12 & 7
        a, b = regs[insn >> 15 & 31], regs[insn >> 20 & 31]
        imm = signed(insn >> 20, 12)
        nxt, value, write = pc+4, 0, False
        if op in [0x13,0x33]:
            rhs = b if op == 0x33 else imm & MASK
            shift = rhs & 31
            value = [lambda: a-rhs if op==0x33 and insn>>30&1 else a+rhs,
                     lambda: a << shift, lambda: int(signed(a)<signed(rhs)), lambda: int(a<rhs),
                     lambda: a^rhs,
                     lambda: signed(a)>>shift if insn>>30&1 else a>>shift,
                     lambda: a|rhs, lambda: a&rhs][f3]() & MASK
            write = True
        elif op in [0x37,0x17]:
            value = ((insn & 0xfffff000)+(pc if op==0x17 else 0)) & MASK
            write = True
        elif op == 3:
            address=(a+imm)&MASK
            size={0:1,1:2,2:4,4:1,5:2}[f3]
            value=int.from_bytes(mem[address:address+size], 'little', signed=f3 in [0,1]) & MASK
            write=True
        elif op == 0x23:
            offset=signed((insn>>25)<<5 | (insn>>7&31),12)
            size=1<<f3
            address=(a+offset)&MASK
            mem[address:address+size]=(b & ((1<<(8*size))-1)).to_bytes(size,'little')
        elif op == 0x63:
            offset=signed((insn>>31)<<12 | (insn>>7&1)<<11 | (insn>>25&63)<<5 | (insn>>8&15)<<1,13)
            taken={0:a==b,1:a!=b,4:signed(a)<signed(b),5:signed(a)>=signed(b),6:a<b,7:a>=b}[f3]
            if taken: nxt=pc+offset
        elif op == 0x6f:
            offset=signed((insn>>31)<<20 | (insn>>12&255)<<12 | (insn>>20&1)<<11 | (insn>>21&1023)<<1,21)
            value, write, nxt=pc+4, True, pc+offset
        elif op == 0x67:
            value, write, nxt=pc+4, True, (a+imm)&~1
        elif op == 0x73:
            yield pc, insn, 0, None
            return
        else:
            raise AssertionError(f'Unsupported instruction {insn:08x}')
        yield pc, insn, rd if write else 0, value if write and rd else None
        if write and rd: regs[rd]=value
        pc=nxt & MASK
    raise AssertionError('Reference program did not terminate')
