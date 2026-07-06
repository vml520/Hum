"""
engine/adapters/logistics.py — delivery windows → ConstraintGraph
──────────────────────────────────────────────────────────────────
Delivery batching as signed MAX-CUT. Two deliveries with overlapping
time windows contribute a positive edge (anti-FM: different truck).
Two deliveries close in space with non-overlapping windows contribute
a negative edge (FM: same truck for routing efficiency).

Structurally identical to the calendar adapter — time is linear rather
than circular, but the MAX-CUT semantics are the same:
  +1 → truck A
  −1 → truck B

Positions:
  2D delivery locations flow through as the winding-diagnostic layout.
  Dense clusters of overlapping deliveries produce vortices (frustrated
  cycles: no 2-truck split exists — need a third truck or drops).
"""
import numpy as np
from ..constraint_graph import ConstraintGraph


def from_delivery_windows(deliveries, buffer_hours=0.0, prox_km=2.0,
                          prox_weight=0.3):
    """
    Build a ConstraintGraph from a list of deliveries.

    Parameters
    ----------
    deliveries    : list of dicts with keys:
                      'id'    : str label
                      'window': (start_hr, end_hr) tuple
                      'loc'   : (x, y) 2D coordinate
    buffer_hours  : minimum gap between deliveries on the same truck
                    (windows tighter than this get a weak anti-FM edge)
    prox_km       : locations closer than this get an FM edge when
                    their time windows don't collide
    prox_weight   : FM edge weight for proximity (kept small so it
                    biases routing efficiency without overriding
                    hard overlap constraints)

    Returns
    -------
    ConstraintGraph with metadata domain="logistics"
    """
    n = len(deliveries)
    W = np.zeros((n, n))
    for i in range(n):
        si, ei = deliveries[i]['window']
        xi, yi = deliveries[i]['loc']
        for j in range(i + 1, n):
            sj, ej = deliveries[j]['window']
            xj, yj = deliveries[j]['loc']
            overlap = max(0.0, min(ei, ej) - max(si, sj))
            gap     = max(0.0, max(si - ej, sj - ei))
            if overlap > 0:
                W[i, j] = W[j, i] = 1.0                # hard: different truck
            elif gap < buffer_hours:
                W[i, j] = W[j, i] = 0.4                # tight: weak anti-FM
            else:
                dist = ((xi - xj)**2 + (yi - yj)**2) ** 0.5
                if dist < prox_km:
                    W[i, j] = W[j, i] = -prox_weight   # same truck efficient

    labels    = [d['id'] for d in deliveries]
    positions = np.array([d['loc'] for d in deliveries], dtype=float)
    return ConstraintGraph(
        W         = W,
        labels    = labels,
        positions = positions,
        metadata  = {"domain":        "logistics",
                     "n_deliveries":  n,
                     "buffer_hours":  buffer_hours,
                     "prox_km":       prox_km},
    )


def simulate_delivery_batch(n=30, seed=0):
    """
    Synthetic delivery batch designed so the overlap graph is bipartite:
    n/2 "wave-A" deliveries with windows staggered every 1 hour, n/2
    "wave-B" deliveries offset by 30 min. Each wave-A[i] overlaps with
    wave-B[i] and wave-B[i-1]; no within-wave overlaps.

    Locations are 2D uniform: proximity FM edges create secondary signal
    for winding diagnostic but do not change the correct 2-truck split.

    Returns: (graph, truth_partition) where truth[i] ∈ {+1, -1}.
    """
    rng = np.random.default_rng(seed)
    half = n // 2
    deliveries = []
    truth = np.zeros(n)

    for i in range(half):
        start = 8.0 + i * 1.0
        loc   = (rng.uniform(0, 10), rng.uniform(0, 10))
        deliveries.append({'id': f"A{i:02d}",
                           'window': (start, start + 0.9),
                           'loc': loc})
        truth[i] = 1

    for i in range(half):
        start = 8.5 + i * 1.0
        loc   = (rng.uniform(0, 10), rng.uniform(0, 10))
        deliveries.append({'id': f"B{i:02d}",
                           'window': (start, start + 0.9),
                           'loc': loc})
        truth[half + i] = -1

    return from_delivery_windows(deliveries), truth
