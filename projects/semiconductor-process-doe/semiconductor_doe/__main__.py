import argparse
import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .oxidation import fit_oxidation, thickness
from .experiment import design, simulate, fit, optimize, RANGES


def main():
    parser = argparse.ArgumentParser(description='Fit oxidation measurements and analyse simulated process experiments')
    parser.add_argument('--data', default='data/oxide_1050.csv')
    parser.add_argument('--output', default='results')
    args = parser.parse_args(); out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    with open(args.data, newline='') as f: rows = list(csv.DictReader(f))
    time = np.array([float(r['time_min'])/60 for r in rows]); initial = np.array([float(r['initial_nm'])/1000 for r in rows]); measured = np.array([float(r['final_nm'])/1000 for r in rows])
    result = fit_oxidation(time, measured, initial)
    print('Oxidation: B/A = %.5g µm/h; B = %.5g µm²/h; RMSE = %.3f nm' % (result['linear'], result['parabolic'], result['rmse']*1000))
    print('Approximate 95%% intervals (B/A, B):', result['ci95'])
    grid = np.linspace(0,max(time),200)
    fig, ax = plt.subplots(); ax.scatter(time*60,measured*1000,label='measurements'); ax.plot(grid*60,thickness(grid,result['linear'],result['parabolic'],initial.mean())*1000,label='fit'); ax.set(xlabel='Time (min)',ylabel='Oxide thickness (nm)',title='Wet oxidation at 1050 °C'); ax.legend(); fig.tight_layout(); fig.savefig(out/'oxidation.png',dpi=150); plt.close(fig)
    x = design()
    for kind,target in [('etch',100),('deposition',80)]:
        rate, uniformity = simulate(x,kind); rb, anova, residual = fit(x,rate); ub, _, _ = fit(x,uniformity); recipe = optimize(rb,ub,target)
        print('\n%s: residual SSE %.3f, df %d' % (kind,*residual))
        print('term, coefficient, partial SS, F, p')
        for row in anova: print('%s, %.4f, %.4f, %.4f, %.4g' % row)
        print('Main and interaction high-minus-low effects = 2 × coefficients; squares are curvature terms.')
        print('Recipe (power W, pressure mTorr, flow sccm):', np.round(recipe['settings'],2), 'rate', round(recipe['rate'],2), 'uniformity',round(recipe['uniformity'],2))
        with open(out/(kind+'_runs.csv'),'w',newline='') as f:
            w=csv.writer(f); w.writerow(['run','power_W','pressure_mTorr','flow_sccm','rate_nm_min','uniformity_percent']);
            for i, (z,r,u) in enumerate(zip(x,rate,uniformity)): w.writerow([i+1,*(RANGES[:,0]+(z+1)/2*(RANGES[:,1]-RANGES[:,0])),r,u])
        g=np.linspace(-1,1,60); a,b=np.meshgrid(g,g); from .experiment import matrix
        points=np.column_stack([a.ravel(),b.ravel(),np.full(a.size,recipe['coded'][2])]); response=(matrix(points,np.zeros(len(points)))@rb).reshape(a.shape)
        fig,ax=plt.subplots(); contour=ax.contourf(150+50*a,40+20*b,response,levels=15); fig.colorbar(contour,ax=ax,label='Rate (nm/min)'); ax.scatter(*recipe['settings'][:2],c='red',label='recipe'); ax.set(xlabel='Power (W)',ylabel='Pressure (mTorr)',title=f'{kind.capitalize()} response at chosen flow'); ax.legend(); fig.tight_layout(); fig.savefig(out/(kind+'_surface.png'),dpi=150); plt.close(fig)

if __name__ == '__main__': main()
