"""
engine/dihedral_solver.py — DihedralSolver: continuous S¹ optimizer
─────────────────────────────────────────────────────────────────────────────
Kuramoto-style coupling + per-vertex basin pinning.  Sibling to WindingSolver:
same phase field, same ConstraintGraph W-sign convention, different pin.

  Coupling:  Σ W_ij sin(θ_j − θ_i)      W_ij > 0 anti-FM, W_ij < 0 FM
                                        (identical to WindingSolver)
  Pinning:   −a_j sin(θ_j − θ*_j)       pulls each vertex to its target
  Noise:     annealed Gaussian          escapes local basins early

Where WindingSolver's binarising pin (−K sin 2θ) locks phases to {0, π} for
hard partition readout, DihedralSolver's basin pin lets each vertex settle
at its own configured target angle — appropriate for protein backbone
dihedrals (φ, ψ) whose Ramachandran-allowed regions are per-residue.

Graph metadata contract:
  graph.metadata["targets"]         : (n,) target angle per vertex, radians
  graph.metadata["pin_strengths"]   : (n,) pinning weight per vertex; 0 means
                                       "no target — dihedral floats freely"
The chain coupling in graph.W (typically FM, W < 0) provides smoothness
between residues within a secondary-structure block.
"""
import numpy as np, time
from .constraint_graph import ConstraintGraph, SolverResult


def _wpi(x):    return ((np.asarray(x) + np.pi) % (2 * np.pi)) - np.pi


class DihedralSolver:
    """
    Continuous-S¹ solver for backbone-dihedral-like problems.

    Parameters
    ----------
    steps    : annealing steps per restart
    restarts : independent restarts (best by energy taken)
    dt       : Euler step size
    seed     : RNG seed
    """

    def __init__(self, steps=2000, restarts=8, dt=0.05, seed=0):
        self.steps    = steps
        self.restarts = restarts
        self.dt       = dt
        self.seed     = seed

    # ── public interface ──────────────────────────────────────────────────────

    def solve(self, graph: ConstraintGraph) -> SolverResult:
        t0  = time.time()
        W   = graph.W
        n   = W.shape[0]
        rng = np.random.default_rng(self.seed)

        targets       = np.asarray(graph.metadata.get("targets",
                                                     np.zeros(n)), dtype=float)
        pin_strengths = np.asarray(graph.metadata.get("pin_strengths",
                                                     np.ones(n)),  dtype=float)

        coup_scale = np.abs(W).sum(1).mean()
        pin_scale  = pin_strengths.mean()
        sig0       = 0.5 * (coup_scale + pin_scale + 1e-9)

        th = rng.uniform(-np.pi, np.pi, (self.restarts, n))

        for step in range(self.steps):
            frac = step / self.steps
            sig  = sig0 * (1 - frac) ** 2
            C, S = np.cos(th), np.sin(th)
            WC   = C @ W;  WS = S @ W
            coup = S * WC - C * WS              # Σ W_ij sin(θ_j − θ_i)
                                                #   W>0 anti-FM, W<0 FM
            pin  = -pin_strengths * np.sin(th - targets)
            th   = _wpi(th + self.dt * (coup + pin)
                        + np.sqrt(self.dt) * sig * rng.normal(0, 1, th.shape))

        # ── restart selection by total energy (lower = better) ────────────────
        best_k = 0; best_E = np.inf
        for k in range(self.restarts):
            th_k = th[k]
            C_k, S_k = np.cos(th_k), np.sin(th_k)
            E_coup = -0.5 * float(C_k @ W @ C_k + S_k @ W @ S_k)
            E_pin  = -float(np.sum(pin_strengths * np.cos(th_k - targets)))
            E      = E_coup + E_pin
            if E < best_E:
                best_E = E; best_k = k

        best_phases = th[best_k].copy()

        return SolverResult(
            partition    = np.sign(np.cos(best_phases)),
            cut_value    = float(-best_E),
            vortex_count = 0,
            tension_map  = [],
            runtime      = time.time() - t0,
            labels       = graph.labels,
            phases       = best_phases,
        )
