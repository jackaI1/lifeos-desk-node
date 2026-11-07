set pagination off
set trace-commands on
set remotetimeout 5
set confirm off
target remote :3333
break firmware_main
monitor start
continue
set variable trigger_fault=1
print trigger_fault
break hardfault_record
break injected_fault
continue
x/i $pc
delete 3
continue
set $fault_pc=frame[6]
printf "Stacked ARM PC: 0x%x\n", $fault_pc
x/i $fault_pc
info registers
python
pc=int(gdb.parse_and_eval('frame[6]'))
text=gdb.execute('x/i '+str(pc),to_string=True)
assert 'udf' in text, text
print('PASS: stacked PC identifies the deliberately injected ARM UDF instruction')
end
disassemble injected_fault
detach
quit
