import argparse
import json
from pathlib import Path
import yaml
from .station import Link, MockResource, run_plan, render_report, train_classifier

parser = argparse.ArgumentParser(description='Run a simulated optical test plan')
parser.add_argument('plan', nargs='?', default='plans/default.yaml')
parser.add_argument('--output', default='report.html')
args = parser.parse_args()
plan = yaml.safe_load(Path(args.plan).read_text())
results = run_plan(plan, MockResource(Link()))
model, evaluation = train_classifier()
for row in results:
    if 'loss_margin_db' in row: row['model_label'] = model.predict([[row['loss_margin_db'], row['osnr_margin_db']]])[0]
Path(args.output).write_text(render_report(results), encoding='utf-8')
print(json.dumps({'results': results, 'evaluation': evaluation}, indent=2))
