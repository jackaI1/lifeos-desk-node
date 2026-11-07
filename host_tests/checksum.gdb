set pagination off
set confirm off
set disable-randomization off
run < host_tests/checksum.wire
bt
frame 4
info locals
python
frames=[]
f=gdb.newest_frame()
while f:
    frames.append(f.name())
    if f.name() == 'checksum_fault':
        f.select()
        raw=f.read_var('raw')
        assert int(raw[2]) == 0
        gdb.execute('x/6bx raw')
        gdb.execute('disassemble /m checksum_fault')
    f=f.older()
assert 'checksum_fault' in frames, frames
print('PASS: deliberately rejected checksum reached the injected crash fixture')
end
quit
