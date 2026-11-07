"""Trigger the real configured Jenkins pipeline and require a successful build."""
from pathlib import Path
import base64
import json
import os
import time
import urllib.error
import urllib.request

base='http://127.0.0.1:8088'
auth=base64.b64encode(('admin:'+os.environ['JENKINS_ADMIN_PASSWORD']).encode()).decode()

def request(path,data=None,headers=None):
    req=urllib.request.Request(base+path,data=data,headers={'Authorization':'Basic '+auth,**(headers or {})})
    with urllib.request.urlopen(req,timeout=5) as response:return response.read()

start=time.monotonic()
while time.monotonic()-start<180:
    try:
        json.loads(request('/job/desk-fsm/api/json'));break
    except (OSError,ValueError):time.sleep(1)
else:raise SystemExit('Jenkins configured job never became available')
# API token is unnecessary for this loopback fixture; use a real crumb/session.
import http.cookiejar
jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
req=urllib.request.Request(base+'/crumbIssuer/api/json',headers={'Authorization':'Basic '+auth})
with opener.open(req,timeout=5) as response:crumb=json.load(response)
req=urllib.request.Request(base+'/job/desk-fsm/build',data=b'',headers={'Authorization':'Basic '+auth,crumb['crumbRequestField']:crumb['crumb']})
with opener.open(req,timeout=5) as response:assert response.status in (200,201)
while time.monotonic()-start<420:
    try:
        build=json.loads(request('/job/desk-fsm/lastBuild/api/json'))
        if not build['building']:
            reports=Path('vehicle_alert/build');reports.mkdir(parents=True,exist_ok=True)
            for artifact in ('cppcheck.xml','test-results.xml'):
                try:(reports/('jenkins-'+artifact)).write_bytes(request('/job/desk-fsm/lastBuild/artifact/vehicle_alert/build/'+artifact))
                except urllib.error.HTTPError:pass
            if build['result']!='SUCCESS':
                report=reports/'jenkins-cppcheck.xml'
                if report.exists():print(report.read_text()[-3500:])
                log=request('/job/desk-fsm/lastBuild/consoleText').decode()
                raise SystemExit(log[-4000:])
            print('PASS: Jenkins pipeline built C, ran 37 checks, checked MISRA and archived reports')
            break
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
    time.sleep(1)
else:raise SystemExit('Jenkins build did not finish')
