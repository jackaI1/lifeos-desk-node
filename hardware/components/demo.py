"""Run a disposable real InvenTree load and verify it twice, always cleaning up."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen

from .__main__ import ROOT, DATA, export
from .inventree import API, load, verify


def run(output, boards=10, bom=None, placements=None):
    output = Path(output).resolve()
    parts, templates, digest = export(output, boards, bom, placements)
    env = dict(os.environ)
    env['DESK_PARTS_PASSWORD'] = secrets.token_urlsafe(32)
    env['DESK_PARTS_SECRET'] = secrets.token_urlsafe(48)
    project = 'desk-parts-' + secrets.token_hex(6)
    compose = ['docker','compose','-f',str(DATA/'compose.yaml'),'-p',project]
    logpath = output/'docker.log'
    ownership = {'owner':'desk-node component database demo', 'runner_pid':os.getpid(),
                 'started_utc':datetime.now(timezone.utc).isoformat(),
                 'docker_context':env.get('DOCKER_CONTEXT','current context'),
                 'project':project,'cleanup':compose + ['down','--volumes','--remove-orphans']}
    (output/'resources.json').write_text(json.dumps(ownership,indent=2)+'\n')
    def command(args, capture=False):
        with logpath.open('ab') as log:
            return subprocess.run(compose + args, env=env, check=True,
                                  stdout=subprocess.PIPE if capture else log, stderr=log,
                                  text=capture, timeout=600).stdout
    try:
        # Dependencies ship in the pinned image. Migrate without an unpinned pip upgrade.
        # InvenTree's startup hook creates the env-configured administrator after migrations.
        command(['run','--rm','inventree','invoke','migrate'])
        command(['run','--rm','inventree','invoke','static'])
        command(['up','-d','inventree'])
        address = command(['port','inventree','8000'], capture=True).strip()
        cid = command(['ps','-q','inventree'], capture=True).strip()
        metadata = subprocess.check_output(['docker','inspect','--format',
                    '{{json .State}}',cid],env=env,text=True)
        state = json.loads(metadata)
        ownership.update(container_id=cid, container_pid=state['Pid'],
                         container_started=state['StartedAt'],address=address)
        (output/'resources.json').write_text(json.dumps(ownership,indent=2)+'\n')
        print(f'Owned InvenTree fixture: project={project}; PID={state["Pid"]}; '
              f'start={state["StartedAt"]}; port={address}; cleanup=docker compose -p {project} down --volumes',flush=True)
        url = 'http://' + address
        for attempt in range(90):
            try:
                with urlopen(url + '/api/',timeout=2) as response:
                    if response.status == 200: break
            except (URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError('InvenTree did not become ready in 90 seconds')
        api = API(url, 'desk-demo', env['DESK_PARTS_PASSWORD'])
        first = load(api,parts,templates,digest)
        first_result = verify(api,first)
        counts = {path:len(api.list(path,refresh=True)) for path in api.cache}
        second = load(api,parts,templates,digest)
        assert first == second, 'Repeated load changed record identities'
        result = verify(api,second)
        assert counts == {path:len(api.list(path,refresh=True)) for path in counts}, 'Repeated load duplicated records'
        result.update(load_passes=2, idempotent=True, pinned_inventree='1.6.2',
                      fitted_components=sum(p['quantity'] for p in parts),bom_sha256=digest)
        (output/'api-verification.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,sort_keys=True),flush=True)
    except BaseException:
        command(['logs','--tail','40'],capture=False)
        print('Docker failure log (last 30 lines):',flush=True)
        print('\n'.join(logpath.read_text(errors='replace').splitlines()[-30:]),flush=True)
        raise
    finally:
        command(['down','--volumes','--remove-orphans'])
        remaining = subprocess.check_output(['docker','ps','-aq','--filter',f'label=com.docker.compose.project={project}'],env=env,text=True).strip()
        volumes = subprocess.check_output(['docker','volume','ls','-q','--filter',f'label=com.docker.compose.project={project}'],env=env,text=True).strip()
        assert not remaining and not volumes, 'Owned Docker resources remain after cleanup'
        ownership['cleanup_verified'] = True
        ownership['remaining_containers'] = 0
        ownership['remaining_volumes'] = 0
        (output/'resources.json').write_text(json.dumps(ownership,indent=2)+'\n')
        print(f'Cleanup verified: {project}: 0 containers and 0 volumes remain.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'hardware/build/components')
    parser.add_argument('--boards',type=int,default=10)
    parser.add_argument('--bom',type=Path)
    parser.add_argument('--placements',type=Path)
    args=parser.parse_args()
    run(args.output,args.boards,args.bom,args.placements)

if __name__ == '__main__':
    main()
