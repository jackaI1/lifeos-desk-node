"""Simplified gasket compression and steady-state thermal estimates."""
import json
import math
import random
import statistics
import sys

def evaluate(p, samples=20000, seed=42):
    names = ('cord', 'cord_tol', 'groove_depth', 'groove_tol', 'lid_gap', 'gap_tol', 'power_w', 'thermal_resistance_k_w')
    if any(not math.isfinite(p[n]) or p[n] < 0 for n in names) or p['cord'] <= p['groove_depth'] + p['lid_gap'] or samples < 2:
        raise ValueError('Invalid gasket or thermal parameters')
    nominal = p['cord'] - p['groove_depth'] - p['lid_gap']
    widths = [('cord', p['cord_tol']), ('groove depth', p['groove_tol']), ('lid gap', p['gap_tol'])]
    total = sum(x[1] for x in widths)
    rng = random.Random(seed)
    sim = [nominal + sum(rng.gauss(0, w/3) for _, w in widths) for _ in range(samples)]
    ranked = sorted(widths, key=lambda x: x[1], reverse=True)
    return {'compression_nominal': nominal, 'compression_worst': (nominal-total, nominal+total), 'lid_gap_worst': (p['lid_gap']-p['gap_tol'], p['lid_gap']+p['gap_tol']), 'compression_sigma': math.sqrt(sum(w*w for _,w in widths))/3, 'simulation_mean': statistics.mean(sim), 'simulation_sigma': statistics.stdev(sim), 'ranked': ranked, 'recommendation': 'Review tolerance on '+ranked[0][0], 'temperature_rise_c': p['power_w']*p['thermal_resistance_k_w']}

if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8') as f: p=json.load(f)
    print(json.dumps(evaluate(p['analysis']), indent=2))
