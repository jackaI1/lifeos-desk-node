"""Deal-Grove growth and nonlinear parameter estimation, in µm and hours."""
import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import t


def thickness(time_h, linear, parabolic, initial=0):
    """Solve x² + A x = B t + x0² + A x0; A = B/(B/A)."""
    time_h, initial = np.asarray(time_h), np.asarray(initial)
    if np.any(time_h < 0) or np.any(initial < 0) or linear <= 0 or parabolic <= 0:
        raise ValueError("time and initial thickness must be nonnegative; rates must be positive")
    a = parabolic / linear
    # Rationalized form avoids cancellation for small thickness.
    c = parabolic * time_h + initial**2 + a * initial
    return 2 * c / (np.sqrt(a*a + 4*c) + a)


def fit_oxidation(time_h, observed, initial=0):
    time_h, observed = np.asarray(time_h, float), np.asarray(observed, float)
    initial = np.broadcast_to(np.asarray(initial, float), time_h.shape)
    if time_h.ndim != 1 or observed.shape != time_h.shape or len(time_h) < 4:
        raise ValueError("at least four paired observations are required")
    if not np.all(np.isfinite([time_h, observed, initial])) or np.any(observed <= 0):
        raise ValueError("measurements must be finite and positive")
    popt, cov = curve_fit(lambda x, l, b: thickness(x, l, b, initial), time_h, observed,
                          p0=(0.3, 0.1), bounds=(1e-10, np.inf), maxfev=50000)
    se = np.sqrt(np.diag(cov)); margin = t.ppf(.975, len(time_h)-2) * se
    return {"linear": popt[0], "parabolic": popt[1], "ci95": np.array([popt-margin, popt+margin]).T,
            "rmse": np.sqrt(np.mean((observed-thickness(time_h, *popt, initial))**2)), "covariance": cov}
