"""
phase1_realdata.py — Real genomic data: chr22:40–40.5 Mb (Ensembl/dbSNP)
──────────────────────────────────────────────────────────────────────────
Uses real SNP positions from the Ensembl REST API (GRCh38, chr22).
Subsample 250 biallelic SNPs preserving the real density distribution —
dense regions stay denser after subsampling, so the tension diagnostic
reflects genuine biological variation.

Reads are simulated (long-read model: 8-SNP window, 15x coverage, 2% error)
because individual-level phased sequencing data requires alignment files not
accessible here. The ground truth haplotype is random, but the POSITIONS
and their density are real.

Key question: does the tension diagnostic show spatial structure that reflects
the real SNP density variation across the 500 kb window?
"""
import numpy as np, sys, json
try:
    import requests
except ImportError:
    sys.exit("pip install requests")

# ── S¹ primitives (inline) ────────────────────────────────────────────────────

def wrap_theta(x):  return np.asarray(x) % (2 * np.pi)
def wrap_to_pi(x):  return ((np.asarray(x) + np.pi) % (2 * np.pi)) - np.pi

def circular_mean(theta):
    return float(np.angle(np.exp(1j * np.asarray(theta)).sum()))

# ── fetch real SNP positions ──────────────────────────────────────────────────

def fetch_snps(chrom="22", start=40_000_000, end=40_500_000, n_sample=250, seed=1):
    """
    Download biallelic SNPs from Ensembl REST API for the given region.
    Subsample to n_sample positions, preserving density distribution
    by taking every kth variant by index (not by position).
    """
    print(f"Fetching variants from Ensembl chr{chrom}:{start:,}–{end:,} …", flush=True)
    url = f"https://rest.ensembl.org/overlap/region/human/{chrom}:{start}-{end}"
    r = requests.get(url,
                     params={"feature": "variation", "content-type": "application/json"},
                     timeout=60)
    r.raise_for_status()
    data = r.json()

    # keep only biallelic SNPs (single-nucleotide substitutions)
    snps = sorted(
        [v for v in data
         if len(v.get("alleles", [])) == 2
         and all(len(a) == 1 for a in v["alleles"])],
        key=lambda v: v["start"]
    )
    print(f"  {len(data):,} total variants → {len(snps):,} biallelic SNPs")

    # subsample every kth by index to preserve density variation
    k = max(1, len(snps) // n_sample)
    sampled = snps[::k][:n_sample]
    positions = np.array([v["start"] for v in sampled])
    ids       = [v["id"] for v in sampled]
    print(f"  Sampled {len(positions)} SNPs  (every {k}th)  "
          f"spanning {positions[-1]-positions[0]:,} bp")
    return positions, ids

# ── simulate diploid reads ────────────────────────────────────────────────────

def simulate_reads(n_snps, coverage=15, read_len=8, error_rate=0.02, seed=0):
    """
    Simulate long-read sequencing over n_snps positions.
    Read length is in SNP count (representing ~15–20 kb physical reads).
    Returns: truth haplotype, signed weight matrix W.
    """
    rng   = np.random.default_rng(seed)
    truth = rng.integers(0, 2, n_snps)
    W     = np.zeros((n_snps, n_snps))
    n_reads = int(coverage * n_snps / read_len)

    for _ in range(n_reads):
        start = rng.integers(0, n_snps - read_len + 1)
        end   = start + read_len
        snps  = np.arange(start, end)
        haplo = truth[snps] if rng.random() < 0.5 else 1 - truth[snps]
        flip  = rng.random(len(snps)) < error_rate
        obs   = np.where(flip, 1 - haplo, haplo)
        for a in range(len(snps)):
            for b in range(a + 1, len(snps)):
                i, j = snps[a], snps[b]
                if obs[a] != obs[b]:
                    W[i, j] += 1; W[j, i] += 1
                else:
                    W[i, j] -= 1; W[j, i] -= 1
    return truth, W

# ── signed winding solver ─────────────────────────────────────────────────────

def signed_winding_solve(W, steps=1500, restarts=12, dt=0.08, K_max=None, seed=0):
    n   = W.shape[0]
    rng = np.random.default_rng(seed)
    abs_deg = np.abs(W).sum(1).mean()
    K_max   = K_max or 1.2 * abs_deg
    th = rng.uniform(0, 2 * np.pi, (restarts, n))
    mid_th = th[0].copy()
    for step in range(steps):
        frac = step / steps
        sig  = 0.8 * abs_deg * (1 - frac) ** 2
        K    = K_max * frac
        C, S = np.cos(th), np.sin(th)
        WC   = C @ W; WS = S @ W
        coup = S * WC - C * WS
        pin  = -K * np.sin(2 * th)
        th   = wrap_theta(th + dt * (coup + pin)
                          + np.sqrt(dt) * sig * rng.normal(0, 1, th.shape))
        if step == steps // 2:
            mid_th = th[0].copy()
    best_s = None; best_sat = -np.inf
    for k in range(restarts):
        s = np.where(np.cos(th[k]) >= 0, 1.0, -1.0)
        s = _polish(W, s)
        sat = _satisfaction(W, s)
        if sat > best_sat:
            best_sat = sat; best_s = s.copy()
    return best_s, mid_th

def _satisfaction(W, s):
    return (np.abs(W).sum() - s @ W @ s) / 4.0

def _polish(W, s):
    s = s.copy(); h = W @ s; improved = True
    while improved:
        improved = False
        g = s * h; i = np.argmax(g)
        if g[i] > 1e-9:
            s[i] = -s[i]; h += 2 * s[i] * W[:, i]; improved = True
    return s

def spectral_round(W):
    L = np.diag(np.abs(W).sum(1)) - W
    _, vecs = np.linalg.eigh(L)
    return _polish(W, np.where(vecs[:, 1] >= 0, 1.0, -1.0))

def majority_vote(W):
    rng = np.random.default_rng(99); best_s = None; best_sat = -np.inf
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

def phasing_accuracy(pred, truth):
    b = (pred > 0).astype(int); h = np.mean(b != truth)
    return 1.0 - min(h, 1.0 - h)

# ── genomic tension map ───────────────────────────────────────────────────────

def genomic_tension_map(mid_th, positions, window_bp=50_000):
    """
    Compute mean phase tension per genomic window using real SNP coordinates.
    tension_i = |wrap_to_pi(θ_{i+1} - θ_i)| — large when neighbouring
    SNPs are in different phase at mid-anneal.
    """
    diffs   = np.abs(wrap_to_pi(np.diff(mid_th)))
    pos_mid = (positions[:-1] + positions[1:]) / 2

    lo = positions[0]; hi = positions[-1]
    windows = []
    w = lo
    while w < hi:
        w_end = w + window_bp
        mask  = (pos_mid >= w) & (pos_mid < w_end)
        t     = float(diffs[mask].mean()) if mask.any() else 0.0
        n_snp = int(mask.sum()) + 1
        windows.append((int(w), int(min(w_end, hi)), t, n_snp))
        w = w_end
    return windows

# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 1. real positions
    positions, ids = fetch_snps()
    n_snps = len(positions)

    # 2. simulate reads
    print(f"\nSimulating reads (15x coverage, read_len=8 SNPs, error=2%) …")
    truth, W = simulate_reads(n_snps, coverage=15, read_len=8, error_rate=0.02)
    total_constraints = int((np.abs(W) > 0).sum() / 2)
    print(f"  Constraint graph: {n_snps} vertices, {total_constraints} edges")
    print(f"  W range: [{W.min():.0f}, {W.max():.0f}]  "
          f"mean |W|={np.abs(W[W!=0]).mean():.2f}")

    # 3. solve
    print("\nRunning solvers …")
    s_w,  mid_th = signed_winding_solve(W)
    s_sp          = spectral_round(W)
    s_mv          = majority_vote(W)

    acc_w  = phasing_accuracy(s_w,  truth)
    acc_sp = phasing_accuracy(s_sp, truth)
    acc_mv = phasing_accuracy(s_mv, truth)

    print(f"\n  winding   accuracy: {acc_w:.4f}")
    print(f"  spectral  accuracy: {acc_sp:.4f}")
    print(f"  majority  accuracy: {acc_mv:.4f}")

    # 4. genomic tension map
    print("\n── Genomic tension map (50 kb windows, real chr22 coordinates) ──")
    print(f"  {'window (Mb)':>18}  snps  tension  density  interpretation")
    windows = genomic_tension_map(mid_th, positions, window_bp=50_000)
    tensions = [t for _, _, t, _ in windows]
    threshold = np.percentile(tensions, 70)
    peak_bp, _, peak_t, _ = max(windows, key=lambda x: x[2])
    for lo, hi, t, n in windows:
        bar  = "█" * int(20 * t / (max(tensions) + 1e-9))
        flag = "← hard to phase" if t >= threshold else ""
        snp_density = n / ((hi - lo) / 1000)      # SNPs per kb
        print(f"  {lo/1e6:.3f}–{hi/1e6:.3f} Mb  {n:4d}  "
              f"{t:.3f}   {snp_density:5.1f}/kb  {bar} {flag}")

    print(f"\n  Peak tension at {peak_bp/1e6:.3f} Mb  ({peak_t:.3f})")
    print(f"  Correlation tension vs SNP density: "
          f"{np.corrcoef([t for _,_,t,_ in windows], [n for _,_,_,n in windows])[0,1]:.3f}")
    print()
    print("If tension correlates with SNP density → dense regions are harder to phase.")
    print("If tension is independent of density → structural (haplotype-level) frustration.")
