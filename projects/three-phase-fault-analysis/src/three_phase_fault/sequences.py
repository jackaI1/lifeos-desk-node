"""Fortescue transform with a = exp(j 120 degrees)."""

import numpy as np

A = np.exp(2j * np.pi / 3)
TO_PHASE = np.array([[1, 1, 1], [1, A**2, A], [1, A, A**2]], dtype=complex)
TO_SEQUENCE = TO_PHASE.conj().T / 3


def _vector(values):
    vector = np.asarray(values, dtype=complex)
    if vector.shape != (3,) or not np.isfinite(vector).all():
        raise ValueError("Expected three finite phasors")
    return vector


def phase_to_sequence(abc):
    """Return [zero, positive, negative] RMS phasors from [a, b, c]."""
    return TO_SEQUENCE @ _vector(abc)


def sequence_to_phase(zero_positive_negative):
    """Return [a, b, c] RMS phasors from [zero, positive, negative]."""
    return TO_PHASE @ _vector(zero_positive_negative)
