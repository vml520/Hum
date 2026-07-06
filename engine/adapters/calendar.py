"""
engine/adapters/calendar.py — scheduling conflicts → ConstraintGraph
─────────────────────────────────────────────────────────────────────
Bridges hum_engine.py's existing calendar parser with the engine interface.

Two entry points:
  from_hum_engine(commits, W_list)   — wraps hum_engine output directly
  from_ics(text)                     — full pipeline from raw .ics text

Partition semantics:
  +1 → keep in current slot / slot A
  −1 → move to a different slot / slot B

Vortex count interpretation:
  0  → all conflicts are pairwise; moving any one event resolves everything
  >0 → frustrated cycles (A↔B↔C↔A): at least vortex_count events cannot all
       be mutually conflict-free with just two slots — needs 3+ slots or drops
"""
import sys, os
import numpy as np

# import hum_engine from the repo root regardless of call location
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, _repo_root)
from hum_engine import parse_ics, to_commitments, build_couplings

from ..constraint_graph import ConstraintGraph


def from_hum_engine(commits, W_list):
    """
    Wrap hum_engine.py's (commits, W) output into a ConstraintGraph.

    W_list is the nested-list W from build_couplings(); it is already
    anti-FM (W>0 for conflicting events → should be in different slots).
    """
    W      = np.array(W_list)
    labels = [c['summary'] for c in commits]
    return ConstraintGraph(
        W        = W,
        labels   = labels,
        metadata = {"domain": "calendar",
                    "cycles": [c['cycle'] for c in commits]},
    )


def from_ics(text):
    """Parse .ics text and return a ConstraintGraph of recurring conflicts."""
    events  = parse_ics(text)
    commits = to_commitments(events)
    W, _    = build_couplings(commits)
    return from_hum_engine(commits, W), commits
