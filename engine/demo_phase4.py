"""
engine/demo_phase4.py — Phase 4 gate: logistics + protein adapters
──────────────────────────────────────────────────────────────────
Validates two more domains through the same ConstraintGraph interface
without any solver changes. The Phase 2 gate (calendar + genetics) is
kept in engine/demo.py; this file adds the two Phase 4 adapters.

Gate criteria:
  Logistics: ≥ 90% of overlapping delivery pairs split across trucks
             on a bipartite synthetic batch (30 deliveries).
  Protein:   ≥ 90% accuracy on 2-domain contact map (100 residues,
             boundary at 60, modularity-signed W).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
from engine.solver import WindingSolver
from engine.adapters.logistics import simulate_delivery_batch
from engine.adapters.protein   import simulate_two_domain


def run_logistics():
    print("══ LOGISTICS ADAPTER ═════════════════════════════════════════════")
    graph, truth = simulate_delivery_batch(n=30, seed=0)
    print(graph.summary())

    solver = WindingSolver(steps=1500, restarts=12, init="auto")
    result = solver.solve(graph)

    part = result.partition
    acc  = max(np.mean(part == truth), np.mean(part == -truth))

    n_correct = 0; n_conflict = 0
    for i in range(graph.n):
        for j in range(i + 1, graph.n):
            if graph.W[i, j] > 0:
                n_conflict += 1
                if part[i] * part[j] < 0:
                    n_correct += 1
    sep = n_correct / n_conflict if n_conflict else 1.0

    print(f"\n  Truth-match acc     : {acc:.4f}  (waves A/B recovery)")
    print(f"  Conflict-edge split : {n_correct}/{n_conflict} = {sep:.4f}")
    print(f"  Vortex count        : {result.vortex_count}")
    print(f"  Cut value           : {result.cut_value:.2f}")
    print(f"  Runtime             : {result.runtime:.2f}s")

    if result.vortex_count == 0:
        print("  Interpretation: 2 trucks fully cover the batch (bipartite).")
    else:
        print(f"  Interpretation: {result.vortex_count} frustrated cycle(s) —"
              " some overlaps unavoidable with 2 trucks.")

    gate = sep >= 0.90
    print(f"\n  Logistics gate: {'PASS (split ≥ 0.90)' if gate else f'FAIL (sep={sep:.3f})'}")
    return gate


def run_protein():
    print("\n══ PROTEIN ADAPTER ═══════════════════════════════════════════════")
    graph, truth, A = simulate_two_domain(n=100, boundary=60, seed=0)
    print(graph.summary())

    solver = WindingSolver(steps=1500, restarts=12, init="auto")
    result = solver.solve(graph)

    part = result.partition
    acc  = max(np.mean(part == truth), np.mean(part == -truth))

    # Estimated boundary: first index where partition sign flips
    signs = part if np.mean(part == truth) >= np.mean(part == -truth) else -part
    flips = np.where(np.diff(signs) != 0)[0]
    est_boundary = int(flips[0] + 1) if len(flips) else None

    print(f"\n  Accuracy       : {acc:.4f}  (true boundary at residue 60)")
    print(f"  Est. boundary  : {est_boundary}")
    print(f"  Vortex count   : {result.vortex_count}")
    print(f"  Cut value      : {result.cut_value:.2f}")
    print(f"  Runtime        : {result.runtime:.2f}s")

    if result.vortex_count <= 2:
        print("  Interpretation: clean 2-domain topology (low frustration).")
    else:
        print(f"  Interpretation: {result.vortex_count} vortices — likely a "
              "multi-domain fold or noisy contacts.")

    gate = acc >= 0.90
    print(f"\n  Protein gate: {'PASS (acc ≥ 0.90)' if gate else f'FAIL (acc={acc:.3f})'}")
    return gate


if __name__ == "__main__":
    log_ok = run_logistics()
    pro_ok = run_protein()

    print("\n══ PHASE 4 GATE ══════════════════════════════════════════════════")
    print(f"  Logistics : {'PASS' if log_ok else 'FAIL'}")
    print(f"  Protein   : {'PASS' if pro_ok else 'FAIL'}")
    overall = log_ok and pro_ok
    print(f"  Overall   : "
          f"{'PASS — 4-domain engine works end-to-end' if overall else 'FAIL — see above'}")
