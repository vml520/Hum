"""
engine/adapters/protein_dihedral.py — secondary structure → ConstraintGraph
─────────────────────────────────────────────────────────────────────────────
Encode a target backbone-dihedral configuration as a ConstraintGraph for
DihedralSolver.  Each residue contributes two vertices — its φ dihedral
and its ψ dihedral — so an n-residue protein becomes 2n vertices.

Vertex layout:
   vertex 2i    = φ_i   (radians in (−π, π])
   vertex 2i+1  = ψ_i

Edges (FM chain coupling for smoothness within secondary-structure blocks):
   W[2i,   2(i+1)]   = w_chain   (φ_i ↔ φ_{i+1})
   W[2i+1, 2(i+1)+1] = w_chain   (ψ_i ↔ ψ_{i+1})

Ramachandran basins (mean angles, degrees):
   'H' α-helix         : (φ, ψ) = (−60,  −45)
   'E' β-sheet         : (φ, ψ) = (−120, +130)
   'L' left-handed α   : (φ, ψ) = (+60,  +45)
   'C' coil / unknown  : no pinning (pin_strength = 0 → dihedral floats
                         under chain coupling from neighbours)

Coil residues are the mechanism by which chain-coupling "matters": their
final angles are inferred from surrounding structured segments.
"""
import numpy as np
from ..constraint_graph import ConstraintGraph


RAMA_BASINS = {
    'H': (np.deg2rad(-60),  np.deg2rad(-45)),
    'E': (np.deg2rad(-120), np.deg2rad(+130)),
    'L': (np.deg2rad(+60),  np.deg2rad(+45)),
    'C': (0.0, 0.0),          # unused when pin_strength = 0
}


def from_secondary_structure(ss, w_chain=0.3, pin_h=1.0, pin_e=1.0,
                             pin_l=1.0, pin_c=0.0):
    """
    Build a ConstraintGraph of 2·len(ss) vertices from a secondary structure
    string.

    Parameters
    ----------
    ss        : string over the alphabet {'H', 'E', 'L', 'C'}
    w_chain   : FM coupling weight between φ_i↔φ_{i+1} and ψ_i↔ψ_{i+1}
    pin_h/e/l : pinning strength for H, E, L residues (higher = tighter)
    pin_c     : pinning strength for coil residues (0 = purely context-driven)

    Returns
    -------
    ConstraintGraph with metadata:
        targets       : (2n,) target angles in radians
        pin_strengths : (2n,) per-vertex pinning weights
        ss            : the original secondary-structure string
    """
    n     = len(ss)
    N     = 2 * n
    W     = np.zeros((N, N))
    tgts  = np.zeros(N)
    pins  = np.zeros(N)

    pin_by_state = {'H': pin_h, 'E': pin_e, 'L': pin_l, 'C': pin_c}
    labels = []
    for i, s in enumerate(ss):
        phi_t, psi_t = RAMA_BASINS.get(s, (0.0, 0.0))
        tgts[2*i]     = phi_t
        tgts[2*i + 1] = psi_t
        pins[2*i]     = pin_by_state.get(s, 0.0)
        pins[2*i + 1] = pin_by_state.get(s, 0.0)
        labels.append(f"φ{i:02d}({s})")
        labels.append(f"ψ{i:02d}({s})")

    for i in range(n - 1):
        W[2*i,     2*(i+1)]     = -w_chain      # FM (negative weight in signed W)
        W[2*(i+1), 2*i]         = -w_chain
        W[2*i + 1, 2*(i+1) + 1] = -w_chain
        W[2*(i+1) + 1, 2*i + 1] = -w_chain

    return ConstraintGraph(
        W        = W,
        labels   = labels,
        metadata = {"domain":        "protein_dihedral",
                    "ss":            ss,
                    "targets":       tgts,
                    "pin_strengths": pins},
    )


def extract_phi_psi(result_phases, ss):
    """Split solver phases back into per-residue (φ, ψ) arrays."""
    phases = np.asarray(result_phases)
    phi = phases[0::2]
    psi = phases[1::2]
    return phi, psi


def in_basin(phi, psi, state, tol_deg=30.0):
    """True iff (φ, ψ) lies within `tol_deg` of state's Ramachandran basin."""
    if state == 'C':
        return True                       # coil is unconstrained by definition
    phi_t, psi_t = RAMA_BASINS[state]
    tol = np.deg2rad(tol_deg)
    d_phi = np.abs(((phi - phi_t + np.pi) % (2*np.pi)) - np.pi)
    d_psi = np.abs(((psi - psi_t + np.pi) % (2*np.pi)) - np.pi)
    return (d_phi < tol) & (d_psi < tol)
