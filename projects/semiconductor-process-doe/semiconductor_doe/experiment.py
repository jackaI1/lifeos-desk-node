"""Augmented half-fraction experiment. All factors are coded from -1 to +1."""
import itertools
import numpy as np
from scipy.stats import f
from scipy.optimize import minimize

NAMES = ['intercept', 'power', 'pressure', 'flow', 'power:pressure', 'power:flow', 'pressure:flow', 'power²', 'pressure²', 'flow²', 'run_order']
RANGES = np.array([[100, 200], [20, 60], [30, 70]])  # W, mTorr, sccm


def design(seed=17):
    # I=ABC half fraction plus its foldover, replicated, and axial/center points.
    first = np.array([(a,b,a*b) for a,b in itertools.product((-1.,1.), repeat=2)])
    fold = first.copy(); fold[:,2] *= -1
    points = np.vstack([first, fold, first, fold, np.eye(3), -np.eye(3), np.zeros((4,3))])
    rng = np.random.default_rng(seed)
    return points[rng.permutation(len(points))]


def matrix(x, order):
    x = np.asarray(x, float); a,b,c = x.T
    return np.column_stack([np.ones(len(x)), a,b,c,a*b,a*c,b*c,a*a,b*b,c*c,order])


def simulate(x, kind, seed=42):
    if kind not in ('etch', 'deposition'): raise ValueError('kind must be etch or deposition')
    rng = np.random.default_rng(seed); n = len(x); order = np.linspace(-1,1,n)
    coeff = {'etch': [100,24,-10,8,5,-3,4,-7,-5,-4,3],
             'deposition': [80,16,7,12,-4,5,-3,-5,-4,-6,-2]}[kind]
    rate = matrix(x, order) @ coeff + rng.normal(0, 2, n)
    # Uniformity is 100 - within-wafer relative spread, in percentage points.
    a,b,c = x.T
    uniformity = 96 - 2*(a-.1)**2 - 1.5*(b+.2)**2 - 1.2*(c-.1)**2 + .3*order + rng.normal(0,.25,n)
    return rate, uniformity


def fit(x, y):
    order = np.linspace(-1,1,len(x)); X = matrix(x, order)
    beta, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    if rank != X.shape[1] or len(y) <= rank: raise ValueError('design needs full rank and residual degrees of freedom')
    residual = y-X@beta; sse = residual@residual; df = len(y)-rank; mse = sse/df
    # Partial F tests compare the full model with each term removed.
    rows = []
    for i in range(1, X.shape[1]):
        reduced = np.delete(X, i, axis=1); pred = reduced @ np.linalg.lstsq(reduced,y,rcond=None)[0]
        ss = max(0., (y-pred)@(y-pred)-sse); stat = ss/mse
        rows.append((NAMES[i], beta[i], ss, stat, f.sf(stat,1,df)))
    return beta, rows, (sse, df)


def optimize(rate_beta, uniformity_beta, target, min_uniformity=93):
    def predict(beta, z): return (matrix(np.array([z]), np.array([0.])) @ beta).item()
    def objective(z): return ((predict(rate_beta,z)-target)/target)**2
    constraint = {'type':'ineq','fun':lambda z: predict(uniformity_beta,z)-min_uniformity}
    results = [minimize(objective, start, method='SLSQP', bounds=[(-1,1)]*3, constraints=[constraint], options={'ftol':1e-12,'maxiter':500}) for start in [np.zeros(3), *np.eye(3), *-np.eye(3)]]
    feasible = [r for r in results if r.success and constraint['fun'](r.x) >= -1e-6]
    if not feasible: raise ValueError('no feasible recipe found within studied range')
    z = min(feasible,key=lambda r:r.fun).x
    return {'coded':z, 'settings':RANGES[:,0]+(z+1)/2*(RANGES[:,1]-RANGES[:,0]), 'rate':predict(rate_beta,z), 'uniformity':predict(uniformity_beta,z)}
