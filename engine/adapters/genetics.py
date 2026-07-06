"""
engine/adapters/genetics.py — SNP reads → ConstraintGraph (chain mode)
────────────────────────────────────────────────────────────────────────
Haplotype phasing as signed MAX-CUT. SNP pairs covered by the same read
contribute a positive edge (different alleles → anti-FM, different haplotype)
or negative edge (same allele → FM, same haplotype).

Chain-mode solver note:
  Phasing produces sparse, locally-connected graphs (each SNP couples only to
  neighbours within read-window distance). Use WindingSolver with init="binary"
  — phases start near {0,π}, letting the anti-FM coupling resolve conflicts
  without the noise of random initialisation overwhelming the weak signal.
  Phase 1 real-data benchmark showed init="binary" is required here.

Positions:
  SNP physical coordinates (bp) are passed as a 1D array; the engine
  computes a 2D layout from them for the winding diagnostic.
"""
import numpy as np
from ..constraint_graph import ConstraintGraph


def from_snp_reads(reads, n_snps, snp_positions=None):
    """
    Build a ConstraintGraph from a list of reads.

    Parameters
    ----------
    reads        : list of dicts, each with keys:
                     'snps'   : list of SNP indices covered
                     'alleles': list of 0/1 allele observations (same length)
    n_snps       : total number of SNP positions
    snp_positions: optional (n_snps,) array of genomic coordinates (bp)

    Returns
    -------
    ConstraintGraph with metadata domain="genetics"
    """
    W = np.zeros((n_snps, n_snps))
    for read in reads:
        snps, alleles = read['snps'], read['alleles']
        for a in range(len(snps)):
            for b in range(a + 1, len(snps)):
                i, j = snps[a], snps[b]
                if alleles[a] != alleles[b]:
                    W[i, j] += 1; W[j, i] += 1    # anti-FM: different haplotype
                else:
                    W[i, j] -= 1; W[j, i] -= 1    # FM: same haplotype

    labels = ([f"SNP_{i}" for i in range(n_snps)] if snp_positions is None
              else [f"{int(p)}" for p in snp_positions])

    positions = None
    if snp_positions is not None:
        # 1D genomic positions → 2D layout: x = position, y = 0 + small noise
        rng = np.random.default_rng(0)
        xs  = (snp_positions - snp_positions.min()) / (snp_positions.max() - snp_positions.min() + 1)
        ys  = rng.normal(0, 0.05, n_snps)
        positions = np.column_stack([xs, ys])

    return ConstraintGraph(
        W         = W,
        labels    = labels,
        positions = positions,
        metadata  = {"domain": "genetics",
                     "n_snps": n_snps,
                     "n_reads": len(reads)},
    )


def simulate_diploid(n_snps=200, coverage=15, read_len=8,
                     error_rate=0.02, seed=0):
    """
    Synthetic haplotype phasing instance with known ground truth.

    Returns: (graph, truth_haplotype, snp_positions)
    """
    rng   = np.random.default_rng(seed)
    truth = rng.integers(0, 2, n_snps)
    snp_positions = np.sort(rng.uniform(0, 500_000, n_snps))

    n_reads = int(coverage * n_snps / read_len)
    reads   = []
    for _ in range(n_reads):
        start  = rng.integers(0, n_snps - read_len + 1)
        end    = start + read_len
        snps   = list(range(start, end))
        haplo  = truth[snps] if rng.random() < 0.5 else 1 - truth[snps]
        flip   = rng.random(read_len) < error_rate
        alleles = list(np.where(flip, 1 - haplo, haplo).astype(int))
        reads.append({'snps': snps, 'alleles': alleles})

    graph = from_snp_reads(reads, n_snps, snp_positions=snp_positions)
    return graph, truth, snp_positions
