"""Own one headless Renode process and its GDB port, including failure cleanup."""
from pathlib import Path
import json
import socket
import subprocess
import time

folder=Path('stm32/build/debug');folder.mkdir(parents=True,exist_ok=True)
with (folder/'renode.log').open('w') as log:
    process=subprocess.Popen(['renode','--disable-xwt','--console','--execute','include @stm32/renode/debug.resc'],stdin=subprocess.PIPE,stdout=log,stderr=log,text=True)
    (folder/'owned-resource.json').write_text(json.dumps(dict(owner='STM32 hardfault test',pid=process.pid,started=time.time(),port=3333,cleanup=f'send quit then SIGTERM to PID {process.pid} and wait')))
    try:
        # Do not probe the GDB TCP port with a throwaway connection: disconnecting
        # that probe lets this Renode version run past the entry breakpoint.
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('Renode exited before GDB was ready')
            transcript=(folder/'renode.log').read_text(errors='replace')
            if 'GDB server with all CPUs started on port :3333' in transcript:break
            time.sleep(.1)
        else:raise TimeoutError('Renode GDB listener did not become ready')
        with (folder/'gdb.txt').open('w') as debugger_log:
            result=subprocess.run(['gdb-multiarch','-q','-batch','-x','stm32/renode/hardfault.gdb','stm32/build/bare.elf'],stdout=debugger_log,stderr=debugger_log,text=True,timeout=60)
        transcript=(folder/'gdb.txt').read_text()
        assert result.returncode==0 and 'PASS: stacked PC' in transcript,transcript[-3000:]
        print('PASS: stacked ARM PC identifies UDF in the real firmware ELF')
    finally:
        if process.poll() is None:
            try:
                process.stdin.write('quit\n');process.stdin.flush();process.wait(timeout=5)
            except (OSError,subprocess.TimeoutExpired):
                process.terminate();process.wait(timeout=10)
        process.stdin.close()
        assert process.poll() is not None
        with socket.socket() as check:
            check.settimeout(.1)
            assert check.connect_ex(('127.0.0.1',3333))!=0,'owned GDB port remained open'
