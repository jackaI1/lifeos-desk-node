import numpy as np
import pytest
from semiconductor_doe.oxidation import thickness, fit_oxidation
from semiconductor_doe.experiment import design, matrix, fit, simulate, optimize, RANGES


def test_oxidation_recovers_rates_and_initial_thickness():
    t = np.linspace(.05, 5, 30); x0 = .02
    y = thickness(t,.3,.12,x0)
    fitted = fit_oxidation(t,y,x0)
    np.testing.assert_allclose([fitted['linear'],fitted['parabolic']],[.3,.12],rtol=1e-5)
    assert thickness(0,.3,.12,x0) == pytest.approx(x0)
    with pytest.raises(ValueError): thickness(-1,.3,.12)


def test_experiment_recovers_effects_and_drift():
    x=design(); coeff=np.array([100,24,-10,8,5,-3,4,-7,-5,-4,3]); y=matrix(x,np.linspace(-1,1,len(x)))@coeff
    beta, _, _ = fit(x,y)
    np.testing.assert_allclose(beta,coeff,atol=1e-9)


def test_recipe_meets_constraints():
    x=design(); r,u=simulate(x,'etch'); rb,_,_=fit(x,r); ub,_,_=fit(x,u)
    recipe=optimize(rb,ub,100,93)
    assert abs(recipe['rate']-100)<.1 and recipe['uniformity']>=93-1e-6
    assert np.all(recipe['settings']>=RANGES[:,0]) and np.all(recipe['settings']<=RANGES[:,1])
