"""
engine/demo_phase5.py — Phase 5 gate: continuous Ramachandran recovery
─────────────────────────────────────────────────────────────────────────────
DihedralSolver takes a 2n-vertex graph (φ_i, ψ_i per residue) with per-vertex
Ramachandran basin targets + FM chain coupling, starts from random dihedrals,
and drives each residue to its correct (φ, ψ) basin.

Gate criterion:
  ≥ 90% of the pinned residues (excluding 'C' coil) end within 30° of their
  Ramachandran basin in both φ and ψ.

This exercises the S¹ solver's continuous-optimization mode — the same phase
field used by WindingSolver for MAX-CUT, driven by a different pin.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
from engine.dihedral_solver             import DihedralSolver
from engine.adapters.protein_dihedral   import (
    from_secondary_structure, extract_phi_psi, in_basin, RAMA_BASINS,
)


def run_dihedral():
    print("══ DIHEDRAL SOLVER (Phase 5) ═════════════════════════════════════")
    ss = "HHHHHHHHHHEEEEEEEEEEHHHHHHHHHH"          # 30-residue α-β-α
    graph = from_secondary_structure(ss, w_chain=0.3,
                                     pin_h=1.0, pin_e=1.0, pin_c=0.0)
    print(graph.summary())
    print(f"  Target sequence: {ss}")

    solver = DihedralSolver(steps=2000, restarts=8, dt=0.05, seed=0)
    result = solver.solve(graph)

    phi, psi = extract_phi_psi(result.phases, ss)

    in_correct = 0; n_pinned = 0
    for i, s in enumerate(ss):
        if s == 'C':
            continue
        n_pinned += 1
        if in_basin(phi[i], psi[i], s, tol_deg=30.0):
            in_correct += 1
    acc = in_correct / max(1, n_pinned)

    print(f"\n  Residues in correct basin: {in_correct}/{n_pinned} = {acc:.4f}")
    print(f"  Energy (−cut_value)      : {-result.cut_value:.2f}")
    print(f"  Runtime                  : {result.runtime:.2f}s")

    print("\n  Per-residue (φ, ψ) in degrees  [target → recovered]:")
    for i, s in enumerate(ss):
        phi_t, psi_t = RAMA_BASINS[s]
        tag = "✓" if s == 'C' or in_basin(phi[i], psi[i], s, 30.0) else "✗"
        print(f"    {tag} R{i:02d} [{s}]  "
              f"target=({np.rad2deg(phi_t):+6.1f}, {np.rad2deg(psi_t):+6.1f})  "
              f"recovered=({np.rad2deg(phi[i]):+6.1f}, {np.rad2deg(psi[i]):+6.1f})")

    gate = acc >= 0.90
    print(f"\n  Dihedral gate: "
          f"{'PASS (≥ 0.90 in basin)' if gate else f'FAIL (acc={acc:.3f})'}")
    return gate


if __name__ == "__main__":
    ok = run_dihedral()
    print("\n══ PHASE 5 GATE ══════════════════════════════════════════════════")
    print(f"  Dihedral : {'PASS' if ok else 'FAIL'}")
    print(f"  Overall  : "
          f"{'PASS — continuous S¹ optimization works' if ok else 'FAIL — see above'}")
