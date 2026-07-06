"""
engine/constraint_graph.py — domain-agnostic constraint interface
──────────────────────────────────────────────────────────────────
ConstraintGraph is the single contract between domain adapters and solvers.
Any domain (scheduling, genetics, logistics, protein) produces a
ConstraintGraph; any solver consumes one and returns a SolverResult.

W[i,j] > 0  vertices i,j should be in DIFFERENT partitions  (anti-FM / conflict)
W[i,j] < 0  vertices i,j should be in SAME partition        (FM / compatible)
W[i,j] = 0  no constraint between i and j
"""
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SolverResult:
    partition:    np.ndarray             # {+1, -1}^n discrete readout (MAX-CUT solvers)
    cut_value:    float                  # total satisfied constraint weight, or -energy
    vortex_count: int                    # topological frustration at mid-anneal
    tension_map:  list                   # [(label_lo, label_hi, tension)] windowed
    runtime:      float                  # seconds
    labels:       Optional[list]         # vertex labels from the ConstraintGraph
    phases:       Optional[np.ndarray] = None   # continuous θ ∈ (−π, π] (dihedral solvers)


class ConstraintGraph:
    """
    Domain-agnostic constraint graph.

    Parameters
    ----------
    W        : (n, n) signed weight matrix (numpy array or nested list)
    labels   : list of n vertex names (SNP IDs, event titles, residue numbers…)
    positions: (n, 2) layout positions for the winding diagnostic (optional;
               spectral layout is computed automatically if None)
    metadata : dict of domain-specific information passed through to results
    """

    def __init__(self, W, labels=None, positions=None, metadata=None):
        self.W         = np.asarray(W, dtype=float)
        n              = self.W.shape[0]
        self.labels    = labels or [str(i) for i in range(n)]
        self.positions = np.asarray(positions) if positions is not None else None
        self.metadata  = metadata or {}
        assert self.W.shape == (n, n), "W must be square"
        assert len(self.labels) == n,  "labels length must match W"

    @property
    def n(self):
        return self.W.shape[0]

    def n_edges(self):
        return int((self.W != 0).sum() // 2)

    def mean_degree(self):
        return float(np.abs(self.W).sum(1).mean())

    def is_sparse(self, threshold=20.0):
        """True when mean weighted degree is below threshold (chain-like graphs)."""
        return self.mean_degree() < threshold

    def summary(self):
        pos = (self.W > 0).sum() // 2
        neg = (self.W < 0).sum() // 2
        return (f"ConstraintGraph  n={self.n}  edges={self.n_edges()}"
                f"  anti-FM={pos}  FM={neg}"
                f"  deg={self.mean_degree():.1f}"
                f"  sparse={self.is_sparse()}"
                f"  domain={self.metadata.get('domain','?')}")
