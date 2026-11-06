"""Local station API and optional failure triage."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
import yaml
from flask import Flask, jsonify, request, send_from_directory, Response
from .fixture import Fixture, FixtureResource
from .station import Link, MockResource, run_plan, render_report, train_classifier

ROOT = Path(__file__).resolve().parent.parent

def create_app():
    app = Flask(__name__, static_folder=None)
    fixture = Fixture()
    @app.get('/')
    def index(): return send_from_directory(ROOT / 'web', 'index.html')
    @app.get('/dashboard.js')
    def dashboard(): return send_from_directory(ROOT / 'web', 'dashboard.js')
    @app.post('/api/fixture')
    def fixture_rpc(): return Response(fixture.handle(request.get_data()), content_type='application/x-protobuf')
    @app.post('/api/run')
    def run():
        data = request.get_json(silent=True) or {}
        try:
            plan = data.get('plan') or yaml.safe_load((ROOT / 'plans/default.yaml').read_text())
            results = run_plan(plan, FixtureResource(Fixture(MockResource(Link(**data.get('link', {}))))))
            model, evaluation = train_classifier()
            for row in results:
                if 'loss_margin_db' in row:
                    row['model_label'] = model.predict([[row['loss_margin_db'], row['osnr_margin_db']]])[0]
            return jsonify(results=results, evaluation=evaluation)
        except (ValueError, TypeError, KeyError) as exc: return jsonify(error=str(exc)), 400
    @app.post('/api/report')
    def report(): return Response(render_report((request.get_json() or {}).get('results', [])), content_type='text/html')
    @app.post('/api/triage')
    def triage():
        data = request.get_json(silent=True) or {}
        advice = 'Check connectors and fibre loss, then repeat the measurement. Inspect OSNR and the noise floor if the result remains low.'
        endpoint, key = os.getenv('TRIAGE_API_URL'), os.getenv('TRIAGE_API_KEY')
        if endpoint and key:
            try:
                payload = json.dumps({'model': os.getenv('TRIAGE_MODEL', 'gpt-4o-mini'), 'messages': [{'role': 'system', 'content': 'Suggest concise diagnostic steps for this simulated optical test. Never change limits.'}, {'role': 'user', 'content': json.dumps(data)}]}).encode()
                req = Request(endpoint, payload, {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
                with urlopen(req, timeout=10) as response: advice = json.load(response)['choices'][0]['message']['content']
                return jsonify(advice=advice, source='llm')
            except Exception: return jsonify(advice=advice, source='fallback', warning='Triage service unavailable')
        return jsonify(advice=advice, source='fallback')
    return app

if __name__ == '__main__': create_app().run(port=5000)
