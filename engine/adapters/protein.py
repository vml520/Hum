"""
engine/adapters/protein.py — residue contact map → ConstraintGraph
──────────────────────────────────────────────────────────────────
Protein domain partitioning as signed MAX-CUT via modularity.

Given a contact matrix A (A[i,j]=1 iff residues i,j are within a
distance cutoff, typically 8 Å for Cα atoms), the Newman-Girvan
modularity is:
    Q = 1/(2m) · Σ_ij (A_ij − k_i k_j / (2m)) · (s_i s_j)
where k_i = Σ_j A_ij and m = Σ_i k_i / 2 = number of contacts.

Maximising Q against s ∈ {±1}^n is exactly signed MAX-CUT with
    W[i,j] = k_i k_j / (2m) − A_ij

  Contact present    → W_ij < 0  (FM edge: same domain)
  Contact absent     → W_ij > 0  (anti-FM: different domain, magnitude
                                   from expected-degree null model)

The anti-FM edges from expected-but-absent contacts break the trivial
"all one domain" degeneracy that pure contact-only FM would have.

Positions:
  Left as None so the solver's spectral layout separates the two
  communities cleanly along the domain boundary — vortex count then
  reads as a true topological difficulty indicator.
"""
import numpy as np
from ..constraint_graph import ConstraintGraph


def from_contact_matrix(A, labels=None):
    """
    Build a ConstraintGraph from a residue contact matrix.

    Parameters
    ----------
    A       : (n, n) symmetric binary matrix, A[i,j]=1 iff residues i,j
              are in contact
    labels  : optional list of n residue labels

    Returns
    -------
    ConstraintGraph with modularity-signed W, domain="protein"
    """
    A = np.asarray(A, dtype=float).copy()
    n = A.shape[0]
    np.fill_diagonal(A, 0)
    k = A.sum(axis=1)
    m = k.sum() / 2.0
    if m < 1e-9:
        W = np.zeros((n, n))
    else:
        W = np.outer(k, k) / (2.0 * m) - A
    np.fill_diagonal(W, 0)

    labels = labels or [f"R{i:03d}" for i in range(n)]
    return ConstraintGraph(
        W        = W,
        labels   = labels,
        metadata = {"domain":       "protein",
                    "n_residues":   n,
                    "n_contacts":   int(m),
                    "formulation":  "modularity"},
    )


def simulate_two_domain(n=100, boundary=60, p_intra=0.15, p_inter=0.015,
                        linker_contacts=3, seed=0):
    """
    Synthetic 2-domain protein contact map.

    Residues [0, boundary) form domain A, [boundary, n) form domain B.
    Intra-domain contacts occur with probability p_intra, inter-domain
    with p_inter, sequence-adjacent (backbone) always in contact, plus
    a few linker contacts spanning the boundary.

    Returns: (graph, truth_partition, contact_matrix)
    """
    rng   = np.random.default_rng(seed)
    A     = np.zeros((n, n))
    truth = np.where(np.arange(n) < boundary, 1.0, -1.0)

    for i in range(n):
        for j in range(i + 1, n):
            same = (truth[i] == truth[j])
            p    = p_intra if same else p_inter
            if rng.random() < p:
                A[i, j] = A[j, i] = 1

    for i in range(n - 1):                       # backbone
        A[i, i+1] = A[i+1, i] = 1

    for _ in range(linker_contacts):
        i = int(rng.integers(max(0, boundary - 3), boundary))
        j = int(rng.integers(boundary, min(n, boundary + 3)))
        A[i, j] = A[j, i] = 1

    graph = from_contact_matrix(A, labels=[f"R{i:03d}" for i in range(n)])
    return graph, truth, A
