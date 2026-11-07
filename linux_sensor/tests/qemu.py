"""Boot actual ARM kernel/modules, requiring explicit UART pass marker and exit."""
import json
from pathlib import Path
import subprocess
import time

command=['qemu-system-arm','-M','vexpress-a9','-m','256M','-nographic','-no-reboot',
    '-kernel','linux_sensor/build/zImage','-dtb','linux_sensor/build/desk.dtb',
    '-drive','file=linux_sensor/build/rootfs.ext2,if=sd,format=raw',
    '-append','console=ttyAMA0 root=/dev/mmcblk0 rw']
start=time.time()
with open('linux_sensor/build/qemu.log','w') as log:
    process=subprocess.Popen(command,stdout=log,stderr=log)
    Path('linux_sensor/build/owned-resource.json').write_text(json.dumps(dict(owner='ARM sensor integration test',pid=process.pid,started=start,port=None,cleanup=f'kill -TERM {process.pid}')))
    try:
        process.wait(timeout=180)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
text=Path('linux_sensor/build/qemu.log').read_text()
assert 'DESK_QEMU_PASS' in text,text[-5000:]
assert 'DESK_QEMU_FAIL' not in text
print('PASS: actual Buildroot ARM kernel, device-tree overlay, I2C and held-alarm character-device tests')
