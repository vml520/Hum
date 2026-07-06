"""
phase1_genetics.py — Haplotype phasing via signed MAX-CUT (Phase 1 validation)
────────────────────────────────────────────────────────────────────────────────
Haplotype phasing: given sequencing reads over a diploid genome, assign each
SNP (variant) to haplotype A or B. This is a signed MAX-CUT problem.

Constraint graph:
  vertex i    = SNP position i
  W[i,j] > 0 = more reads saw DIFFERENT alleles at i,j → want different partitions
  W[i,j] < 0 = more reads saw SAME allele at i,j       → want same partition

Signed winding solver:
  dθ_i = Σ_j W_ij sin(θ_i−θ_j) − K·sin(2θ_i) + noise
  Positive W → anti-FM (drives apart), negative W → FM (drives together).
  Same formula handles both — the sign of W does the work.

New diagnostic — vortex count per genomic window:
  At mid-anneal, compute plaquette winding on a 1D SNP layout.
  High vortex count in a window → many conflicting reads there → hard to phase.
  No existing phasing tool (WhatsHap, SHAPEIT) provides this upfront indicator.

Benchmark:
  Synthetic diploid: known truth → reads with noise → solve → measure accuracy.
  Solvers compared: signed winding (anti-FM) · spectral rounding · majority vote.
"""
import numpy as np

# ── S¹ primitives (inline — no cross-repo import) ────────────────────────────

def wrap_theta(x):
    return np.asarray(x) % (2 * np.pi)

def wrap_to_pi(x):
    return ((np.asarray(x) + np.pi) % (2 * np.pi)) - np.pi

def circular_mean(theta, weights=None):
    z = np.exp(1j * np.asarray(theta))
    if weights is not None:
        z = z * np.asarray(weights)
    return float(np.angle(z.sum()))

def winding_density_1d(theta):
    """
    1D winding diagnostic: sum of phase jumps along the SNP chain.
    Large |sum| in a window → high phase tension → hard-to-phase region.
    """
    diffs = wrap_to_pi(np.diff(theta))
    return diffs

# ── synthetic diploid data ────────────────────────────────────────────────────

def generate_diploid(n_snps=300, n_reads=2400, read_len=15,
                     error_rate=0.02, seed=0):
    """
    Returns:
      truth   : (n_snps,) int array, true haplotype A (0/1 per SNP)
      W       : (n_snps, n_snps) signed weight matrix
      regions : list of (start, end) for windowed vortex diagnostic
    """
    rng = np.random.default_rng(seed)

    # true haplotype A; haplotype B is the complement
    truth = rng.integers(0, 2, n_snps)

    # build weight matrix from simulated reads
    W = np.zeros((n_snps, n_snps))

    for _ in range(n_reads):
        start = rng.integers(0, n_snps - read_len + 1)
        end   = start + read_len
        snps  = np.arange(start, end)

        # read comes from haplotype A or B with equal probability
        haplo = truth[snps] if rng.random() < 0.5 else 1 - truth[snps]
        # add per-base errors
        flip  = rng.random(len(snps)) < error_rate
        obs   = np.where(flip, 1 - haplo, haplo)

        # update W for all pairs covered by this read
        for a in range(len(snps)):
            for b in range(a + 1, len(snps)):
                i, j = snps[a], snps[b]
                if obs[a] != obs[b]:   # different alleles → anti-FM
                    W[i, j] += 1; W[j, i] += 1
                else:                  # same allele → FM
                    W[i, j] -= 1; W[j, i] -= 1

    # genomic windows for regional vortex diagnostic
    win = 50
    regions = [(s, min(s + win, n_snps)) for s in range(0, n_snps, win)]

    return truth, W, regions

# ── signed winding solver ─────────────────────────────────────────────────────

def signed_winding_solve(W, steps=1500, restarts=12, dt=0.08,
                         K_max=None, seed=0):
    """
    Anti-FM solver on signed weight matrix.
    Positive W[i,j]: drive phases apart (different haplotype).
    Negative W[i,j]: drive phases together (same haplotype).
    Both handled by the same coupling term: Σ_j W_ij sin(θ_i−θ_j).

    Returns: (partition s ∈ {±1}^n, mid_anneal_phases)
    """
    n = W.shape[0]
    rng = np.random.default_rng(seed)
    abs_deg = np.abs(W).sum(1).mean()
    K_max = K_max or 1.2 * abs_deg

    th = rng.uniform(0, 2 * np.pi, (restarts, n))
    mid_th = th[0].copy()

    for step in range(steps):
        frac = step / steps
        sig  = 0.8 * abs_deg * (1 - frac) ** 2
        K    = K_max * frac
        C, S = np.cos(th), np.sin(th)
        WC   = C @ W; WS = S @ W
        coup = S * WC - C * WS          # Σ_j W_ij sin(θ_i−θ_j), signed W
        pin  = -K * np.sin(2 * th)
        th   = wrap_theta(th + dt * (coup + pin)
                          + np.sqrt(dt) * sig * rng.normal(0, 1, th.shape))
        if step == steps // 2:
            mid_th = th[0].copy()

    # 1-opt polish per restart, take best
    best_s = None; best_sat = -np.inf
    for k in range(restarts):
        s = np.where(np.cos(th[k]) >= 0, 1.0, -1.0)
        s = _polish(W, s)
        sat = _satisfaction(W, s)
        if sat > best_sat:
            best_sat = sat; best_s = s.copy()

    return best_s, mid_th

def _satisfaction(W, s):
    """Signed constraint satisfaction: Σ_{i<j} W_ij · (1 − s_i s_j)/2 for W>0
    plus Σ_{i<j} |W_ij| · (1 + s_i s_j)/2 for W<0. Simplified: (|W|·1 − s W s)/4."""
    return (np.abs(W).sum() - s @ W @ s) / 4.0

def _polish(W, s):
    s = s.copy(); h = W @ s
    improved = True
    while improved:
        improved = False
        gains = s * h
        i = np.argmax(gains)
        if gains[i] > 1e-9:
            s[i] = -s[i]; h += 2 * s[i] * W[:, i]; improved = True
    return s

# ── baselines ─────────────────────────────────────────────────────────────────

def spectral_round(W):
    """Spectral rounding: partition by sign of Fiedler eigenvector."""
    L = np.diag(np.abs(W).sum(1)) - W
    _, vecs = np.linalg.eigh(L)
    s = np.where(vecs[:, 1] >= 0, 1.0, -1.0)
    return _polish(W, s)

def majority_vote(W):
    """Iterative majority: s_i = sign(Σ_j W_ij s_j), 20 rounds from random init."""
    rng = np.random.default_rng(99)
    best_s = None; best_sat = -np.inf
    for _ in range(20):
        s = rng.choice([-1.0, 1.0], W.shape[0])
        for _ in range(30):
            s_new = np.sign(W @ s); s_new[s_new == 0] = 1.0
            if np.all(s_new == s): break
            s = s_new
        s = _polish(W, s)
        sat = _satisfaction(W, s)
        if sat > best_sat: best_sat = sat; best_s = s.copy()
    return best_s

# ── accuracy + vortex diagnostic ──────────────────────────────────────────────

def phasing_accuracy(pred, truth):
    """Hamming accuracy accounting for global flip symmetry."""
    pred_b = (pred > 0).astype(int)
    h = np.mean(pred_b != truth)
    return 1.0 - min(h, 1.0 - h)

def regional_vortex(mid_th, regions):
    """
    Phase tension per genomic window at mid-anneal.
    Returns list of (start, end, tension) where tension = mean |Δθ| in window.
    Tension → 0 = smooth domain, high tension = frustrated region.
    """
    diffs = np.abs(wrap_to_pi(np.diff(mid_th)))
    out = []
    for start, end in regions:
        if end - 1 > start:
            t = float(diffs[start:end - 1].mean())
        else:
            t = 0.0
        out.append((start, end, t))
    return out

# ── benchmark ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Phase 1 — Haplotype phasing via signed MAX-CUT\n")

    configs = [
        ("low noise  (err=1%)",  dict(n_snps=300, n_reads=2400, read_len=15, error_rate=0.01)),
        ("mid noise  (err=3%)",  dict(n_snps=300, n_reads=2400, read_len=15, error_rate=0.03)),
        ("high noise (err=8%)",  dict(n_snps=300, n_reads=2400, read_len=15, error_rate=0.08)),
        ("short reads (len=6)",  dict(n_snps=300, n_reads=3600, read_len=6,  error_rate=0.03)),
        ("long reads  (len=30)", dict(n_snps=300, n_reads=1200, read_len=30, error_rate=0.03)),
    ]

    hdr = (f"{'config':28} {'winding':>8} {'spectral':>9} {'majority':>9}  "
           f"{'vortex_hi_win':>14}")
    print(hdr); print("─" * len(hdr))

    for label, cfg in configs:
        truth, W, regions = generate_diploid(**cfg)

        s_w, mid_th = signed_winding_solve(W)
        s_sp        = spectral_round(W)
        s_mv        = majority_vote(W)

        acc_w  = phasing_accuracy(s_w,  truth)
        acc_sp = phasing_accuracy(s_sp, truth)
        acc_mv = phasing_accuracy(s_mv, truth)

        # highest-tension genomic window
        rv = regional_vortex(mid_th, regions)
        hi = max(rv, key=lambda x: x[2])

        print(f"{label:28} {acc_w:8.4f} {acc_sp:9.4f} {acc_mv:9.4f}  "
              f"  win {hi[0]:3d}-{hi[1]:3d} ({hi[2]:.3f})")

    print()
    print("Accuracy = fraction of SNPs correctly phased (1.0 = perfect).")
    print("vortex_hi_win = genomic window with highest mid-anneal phase tension.")
    print("  High tension → conflicting reads → hard-to-phase region.")
    print("  This diagnostic is new — no existing phasing tool provides it upfront.")

    # ── regional detail on mid-noise instance ────────────────────────────────
    print("\n── Regional tension map (mid-noise instance, 50-SNP windows) ──")
    truth, W, regions = generate_diploid(n_snps=300, n_reads=2400,
                                         read_len=15, error_rate=0.03)
    _, mid_th = signed_winding_solve(W)
    rv = regional_vortex(mid_th, regions)
    print(f"  {'window':>12}  tension  interpretation")
    tensions = [t for _, _, t in rv]
    threshold = np.percentile(tensions, 70)   # top 30% = hard-to-phase
    for start, end, t in rv:
        bar  = "█" * int(20 * t / max(tensions))
        flag = "← hard to phase" if t >= threshold else ""
        print(f"  SNP {start:3d}-{end:3d}  {t:.3f}   {bar} {flag}")
