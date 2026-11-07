"""Run against Net-SNMP itself on Linux, not a fake SNMP client."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import pytest
from networking.snmp import BASE


@pytest.mark.skipif(os.getenv('DESK_SNMP') != '1', reason='CI installs Net-SNMP')
def test_real_snmp_agent(tmp_path):
    snapshot = tmp_path/'snapshot.json'
    snapshot.write_text(json.dumps(dict(status=1, latency_ms=37, loss_percent=25, alarm=1, updated=time.time())))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    config = tmp_path/'snmpd.conf'
    config.write_text(f'agentaddress udp:127.0.0.1:{port}\nrocommunity desk-demo 127.0.0.1\npass_persist {BASE} {sys.executable} -m networking.snmp {snapshot}\n')
    with (tmp_path/'agent.log').open('w') as log:
        process = subprocess.Popen([shutil.which('snmpd'), '-f', '-Lo', '-C', '-c', str(config)], stdout=log, stderr=log)
        try:
            for _ in range(30):
                result = subprocess.run(['snmpget', '-v2c', '-c', 'desk-demo', '-On', '-t', '.1', '-r', '0', f'127.0.0.1:{port}', BASE+'.2.0'], capture_output=True, text=True)
                if result.returncode == 0: break
                time.sleep(.05)
            assert result.returncode == 0, (result.stderr, (tmp_path/'agent.log').read_text()[-2000:])
            assert 'INTEGER: 37' in result.stdout
            result = subprocess.run(['snmpwalk', '-v2c', '-c', 'desk-demo', '-On', '-t', '1', '-r', '0', f'127.0.0.1:{port}', BASE], capture_output=True, text=True, check=True)
            assert result.stdout.count('INTEGER:') == 4
        finally:
            process.terminate()
            process.wait(timeout=5)
