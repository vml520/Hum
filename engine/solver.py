"""
engine/solver.py — WindingSolver: anti-FM phase solver + winding diagnostic
─────────────────────────────────────────────────────────────────────────────
Coupling: +Σ W_ij sin(θ_i−θ_j)  [anti-aligns phases → correct for MAX-CUT]
Pinning:  −K·sin(2θ_i)          [locks phases to {0,π} → hard partition]
Noise:    annealed Gaussian      [escapes local minima early]

Two initialisation modes selected automatically:
  "binary"  — start near {0,π}; best for sparse/chain-like graphs (genetics)
  "random"  — start uniform [0,2π]; best for dense graphs (scheduling, MAX-CUT)
  auto      — binary if graph.is_sparse(), else random

Winding diagnostic (vortex count):
  At mid-anneal, project phases onto the 2D spectral layout and count
  plaquette winding numbers. Low = clean bipartite domain wall (easy).
  High = frustrated cycles (hard; needs >2 partitions or some constraints dropped).
"""
import numpy as np, time
from .constraint_graph import ConstraintGraph, SolverResult


def _wrap(x):   return np.asarray(x) % (2 * np.pi)
def _wpi(x):    return ((np.asarray(x) + np.pi) % (2 * np.pi)) - np.pi
def _cmean(th): return float(np.angle(np.exp(1j * np.asarray(th)).sum()))


class WindingSolver:
    """
    Anti-FM winding-number solver.

    Parameters
    ----------
    steps    : annealing steps per restart
    restarts : independent restarts (best taken)
    dt       : Euler step size
    K_max    : binarising strength (default: 1.2 × mean_degree)
    seed     : RNG seed
    init     : "binary" | "random" | "auto"
    grid_n   : winding diagnostic grid resolution
    """

    def __init__(self, steps=1500, restarts=12, dt=0.08,
                 K_max=None, seed=0, init="auto", grid_n=16):
        self.steps    = steps
        self.restarts = restarts
        self.dt       = dt
        self.K_max    = K_max
        self.seed     = seed
        self.init     = init
        self.grid_n   = grid_n

    # ── public interface ──────────────────────────────────────────────────────

    def solve(self, graph: ConstraintGraph) -> SolverResult:
        t0  = time.time()
        W   = graph.W
        pos = graph.positions if graph.positions is not None \
              else self._spectral_layout(W)

        best_s, mid_th = self._anneal(W, graph)
        vortex         = self._winding_count(mid_th, pos)
        tension        = self._tension_map(mid_th, graph.labels)
        cut            = self._satisfaction(W, best_s)

        return SolverResult(
            partition    = best_s,
            cut_value    = cut,
            vortex_count = vortex,
            tension_map  = tension,
            runtime      = time.time() - t0,
            labels       = graph.labels,
        )

    # ── annealing core ────────────────────────────────────────────────────────

    def _anneal(self, W, graph):
        n   = W.shape[0]
        rng = np.random.default_rng(self.seed)
        deg = np.abs(W).sum(1).mean()
        K   = self.K_max or 1.2 * deg

        structural_deg = float((W != 0).sum(1).mean())
        chain = (self.init == "binary" or
                 (self.init == "auto" and structural_deg < 20.0))

        # Chain graphs (genetics, protein backbone, 1D-adjacent connectivity):
        #   sin(θ_i−θ_j)→0 near {0,π} so ANY binarising kills information
        #   flow: coupling vanishes exactly at the fixed points before it can
        #   propagate corrections along the chain.  Fix: K=0 throughout —
        #   pure anti-FM coupling + noise annealing, readout via sign(cos θ).
        #   The best restart among N reliably finds the correct partition.
        #   Dense graphs (scheduling, MAX-CUT): standard K·frac schedule.
        if chain:
            W_eff  = W
            K      = 0.0                    # no binarising for chain graphs
        else:
            W_eff = W
            K = self.K_max or 1.2 * deg

        th = rng.uniform(0, 2 * np.pi, (self.restarts, n))
        mid_th = th[0].copy()

        for step in range(self.steps):
            frac = step / self.steps
            sig  = 0.8 * deg * (1 - frac) ** 2
            Ks = K * frac               # chain: K=0 so Ks=0 throughout
            C, S = np.cos(th), np.sin(th)
            WC   = C @ W_eff;  WS = S @ W_eff
            coup = S * WC - C * WS          # +Σ W_ij sin(θ_i−θ_j) anti-FM
            pin  = -Ks * np.sin(2 * th)
            th   = _wrap(th + self.dt * (coup + pin)
                         + np.sqrt(self.dt) * sig * rng.normal(0, 1, th.shape))
            if step == self.steps // 2:
                mid_th = th[0].copy()

        best_s = None; best_sat = -np.inf
        for k in range(self.restarts):
            s = np.where(np.cos(th[k]) >= 0, 1.0, -1.0)
            s = self._polish(W, s)
            sat = self._satisfaction(W, s)
            if sat > best_sat:
                best_sat = sat; best_s = s.copy()
        return best_s, mid_th

    # ── winding diagnostic ────────────────────────────────────────────────────

    def _spectral_layout(self, W):
        L = np.diag(np.abs(W).sum(1)) - W
        _, vecs = np.linalg.eigh(L)
        pos = vecs[:, 1:3].copy()
        scale = np.abs(pos).max(axis=0, keepdims=True) + 1e-9
        return pos / scale

    def _winding_count(self, theta, pos, grid_n=None):
        g = grid_n or self.grid_n
        xs, ys = pos[:, 0], pos[:, 1]
        x_lo, x_hi = xs.min() - .05, xs.max() + .05
        y_lo, y_hi = ys.min() - .05, ys.max() + .05
        gx = np.clip(((xs - x_lo) / (x_hi - x_lo) * g).astype(int), 0, g - 1)
        gy = np.clip(((ys - y_lo) / (y_hi - y_lo) * g).astype(int), 0, g - 1)
        grid = np.full((g, g), np.nan)
        for row in range(g):
            for col in range(g):
                mask = (gx == col) & (gy == row)
                if mask.any():
                    grid[row, col] = _wrap(float(_cmean(theta[mask])))
        fill = _wrap(float(_cmean(theta)))
        grid = np.where(np.isnan(grid), fill, grid)
        w_map = self._plaquette_winding(grid)
        return int(np.abs(w_map).sum())

    @staticmethod
    def _plaquette_winding(grid):
        ny, nx = grid.shape
        w = np.zeros((ny - 1, nx - 1), dtype=int)
        for i in range(ny - 1):
            for j in range(nx - 1):
                loop = (grid[i, j], grid[i, j+1],
                        grid[i+1, j+1], grid[i+1, j])
                s = sum(_wpi(b - a)
                        for a, b in zip(loop, loop[1:] + loop[:1]))
                w[i, j] = int(np.round(s / (2 * np.pi)))
        return w

    def _tension_map(self, mid_th, labels, n_buckets=6):
        """Divide vertices into n_buckets by label order; report mean |Δθ| per bucket."""
        n     = len(mid_th)
        size  = max(1, n // n_buckets)
        diffs = np.abs(_wpi(np.diff(mid_th)))
        out   = []
        for b in range(n_buckets):
            lo  = b * size
            hi  = min(lo + size, n)
            if hi <= lo: break
            t   = float(diffs[lo: hi - 1].mean()) if hi - lo > 1 else 0.0
            out.append((labels[lo], labels[hi - 1], t))
        return out

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _satisfaction(W, s):
        return (np.abs(W).sum() - s @ W @ s) / 4.0

    @staticmethod
    def _polish(W, s):
        s = s.copy(); h = W @ s; improved = True
        while improved:
            improved = False
            g = s * h; i = int(np.argmax(g))
            if g[i] > 1e-9:
                s[i] = -s[i]; h += 2 * s[i] * W[:, i]; improved = True
        return s
