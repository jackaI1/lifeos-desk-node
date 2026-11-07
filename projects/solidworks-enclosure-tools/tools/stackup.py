"""Bounded independent uniform tolerances, not a capability study."""
import argparse
import itertools
import json
import pathlib
import numpy as np


def compression(thickness,depth,gap):
    if thickness<=0: raise ValueError('Gasket thickness must be positive')
    return (thickness-depth-gap)/thickness


def worst_case(t,d,g,dt,dd,dg):
    values=[compression(t+a*dt,d+b*dd,g+c*dg) for a,b,c in itertools.product([-1,1],repeat=3)]
    return dict(min=min(values),max=max(values),nominal=compression(t,d,g))


def monte_carlo(t,d,g,dt,dd,dg,samples=50000,seed=20261106,gap_components=None):
    if samples<2: raise ValueError('Need at least two samples')
    rng=np.random.default_rng(seed)
    x=rng.uniform(-1,1,(samples,3))*[dt,dd,dg]+[t,d,g]
    if gap_components is not None:
        x[:,2]=g
        for limit in gap_components: x[:,2]+=rng.uniform(-limit,limit,samples)
    if np.any(x[:,0]<=0): raise ValueError('Nonpositive thickness sample')
    y=(x[:,0]-x[:,1]-x[:,2])/x[:,0]
    return dict(samples=samples,seed=seed,distribution='independent bounded uniform',
                min=float(y.min()),max=float(y.max()),mean=float(y.mean()),std=float(y.std(ddof=1)),
                p01=float(np.quantile(y,.01)),p99=float(np.quantile(y,.99)))


def thermal(power,area,h):
    if min(area,h)<=0 or power<0: raise ValueError('Invalid thermal assumptions')
    return power/(area*h)


def run(spec):
    t=spec['gasket_thickness_mm'];d=spec['groove_depth_mm'];g=spec['lid_gap_mm']
    dt=spec['gasket_tolerance_mm'];dd=spec['depth_tolerance_mm'];dg=spec['housing_height_tolerance_mm']+spec['shoulder_height_tolerance_mm']
    wc=worst_case(t,d,g,dt,dd,dg)
    mc=monte_carlo(t,d,g,dt,dd,dg,samples=spec['monte_carlo_samples'],seed=spec['random_seed'],gap_components=[spec['housing_height_tolerance_mm'],spec['shoulder_height_tolerance_mm']])
    # First-order variance contribution under independent uniform distributions.
    sensitivity={'gasket_thickness':(d+g)/t**2,'groove_depth':-1/t,'housing_height':1/t,'shoulder_height':-1/t}
    tolerances=dict(zip(sensitivity,[dt,dd,spec['housing_height_tolerance_mm'],spec['shoulder_height_tolerance_mm']]));variance={k:(sensitivity[k]*v)**2/3 for k,v in tolerances.items()}
    total=sum(variance.values())
    contributors=sorted([dict(name=k,variance=v,fraction=v/total if total else 0) for k,v in variance.items()],key=lambda x:-x['variance'])
    # Gap is shoulder height minus body height, nominally g.
    dh=spec['housing_height_tolerance_mm'];ds=spec['shoulder_height_tolerance_mm']
    rng=np.random.default_rng(spec['random_seed']);gap=g+rng.uniform(-ds,ds,spec['monte_carlo_samples'])-rng.uniform(-dh,dh,spec['monte_carlo_samples'])
    l,w,h=[spec[k]/1000 for k in ['length_mm','width_mm','height_mm']]
    area=2*(l*w+l*h+w*h);rise=thermal(spec['power_W'],area,spec['convection_W_m2K'])
    # Compression and lid gap share the same absolute-height worst-case stack.
    return dict(compression=dict(worst_case=wc,monte_carlo=mc,contributors=contributors,
                target=[spec['compression_min'],spec['compression_max']],
                passes=wc['min']>=spec['compression_min'] and wc['max']<=spec['compression_max'],
                note='Gap tolerance is the sum of independent housing and shoulder height limits; all limits are unverified design assumptions.'),
                lid_gap=dict(nominal_mm=g,worst_min_mm=g-ds-dh,worst_max_mm=g+ds+dh,
                    monte_carlo_mean_mm=float(gap.mean()),p01_mm=float(np.quantile(gap,.01)),p99_mm=float(np.quantile(gap,.99)),
                    contributors=sorted([dict(name='housing_height',variance_mm2=dh**2/3),dict(name='shoulder_height',variance_mm2=ds**2/3)],key=lambda x:-x['variance_mm2'])),
                thermal=dict(power_W=spec['power_W'],area_m2=area,h_W_m2K=spec['convection_W_m2K'],rise_K=rise,
                    ambient_C=spec['ambient_C'],estimated_surface_C=spec['ambient_C']+rise,
                    note='Single uniform node, natural convection on all external area. No internal hotspot, radiation, conduction or sealing model. Not tested.'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('spec');p.add_argument('output');a=p.parse_args()
    path=pathlib.Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(run(json.loads(pathlib.Path(a.spec).read_text())),indent=2)+'\n')
