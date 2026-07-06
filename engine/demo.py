"""
engine/demo.py — Phase 2 gate: both adapters produce correct results
─────────────────────────────────────────────────────────────────────
Runs calendar and genetics adapters through the engine interface and
validates that the ConstraintGraph abstraction works end-to-end for
both domains without changes to the solver or the interface.

Gate criteria:
  Calendar: hard partition identifies the known conflicting event pairs;
            vortex count gives an upfront difficulty indicator.
  Genetics: accuracy ≥ 0.75 on synthetic instance (read_len=15, 2% error).
            Denser coverage (structural_deg≈26) gives enough per-pair SNR
            for satisfaction-based restart selection to track the true
            partition. Phase 1 baseline (read_len=8, random init): 0.59.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
from engine.solver import WindingSolver
from engine.adapters.calendar import from_ics
from engine.adapters.genetics import simulate_diploid

# ── hum_engine demo calendar (same as hum_engine.py --demo) ──────────────────
DEMO_ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Exec staff sync
DTSTART:20260615T090000
DTEND:20260615T100000
RRULE:FREQ=WEEKLY;BYDAY=MO
END:VEVENT
BEGIN:VEVENT
SUMMARY:EMEA standup
DTSTART:20260615T093000
DTEND:20260615T100000
RRULE:FREQ=WEEKLY;BYDAY=MO
END:VEVENT
BEGIN:VEVENT
SUMMARY:1:1 with CFO
DTSTART:20260617T140000
DTEND:20260617T143000
RRULE:FREQ=WEEKLY;BYDAY=WE
END:VEVENT
BEGIN:VEVENT
SUMMARY:Board prep
DTSTART:20260617T143000
DTEND:20260617T160000
RRULE:FREQ=WEEKLY;BYDAY=WE
END:VEVENT
BEGIN:VEVENT
SUMMARY:Product review
DTSTART:20260619T110000
DTEND:20260619T120000
RRULE:FREQ=WEEKLY;BYDAY=FR
END:VEVENT
BEGIN:VEVENT
SUMMARY:Investor call
DTSTART:20260619T113000
DTEND:20260619T123000
RRULE:FREQ=WEEKLY;BYDAY=FR
END:VEVENT
BEGIN:VEVENT
SUMMARY:Morning focus block
DTSTART:20260615T080000
DTEND:20260615T083000
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR"""


def run_calendar():
    print("══ CALENDAR ADAPTER ══════════════════════════════════════════════")
    graph, commits = from_ics(DEMO_ICS)
    print(graph.summary())

    solver = WindingSolver(steps=1500, restarts=8)
    result = solver.solve(graph)

    print(f"\n  Vortex count  : {result.vortex_count}")
    print(f"  Cut value     : {result.cut_value:.2f}  "
          f"(max possible: {np.abs(graph.W).sum()/4:.2f})")
    print(f"  Runtime       : {result.runtime:.2f}s")

    if result.vortex_count == 0:
        print("  Interpretation: conflicts are all pairwise — 2 time slots suffice.")
    else:
        print(f"  Interpretation: {result.vortex_count} frustrated cycle(s) — "
              f"needs >2 slots or events dropped.")

    print("\n  Partition (which events move to slot B):")
    slot_a = [result.labels[i] for i, s in enumerate(result.partition) if s > 0]
    slot_b = [result.labels[i] for i, s in enumerate(result.partition) if s < 0]
    print(f"    Slot A  ({len(slot_a)}): {', '.join(slot_a)}")
    print(f"    Slot B  ({len(slot_b)}): {', '.join(slot_b)}")

    # validate: conflicting pairs should be in different slots
    n_correct = 0; n_conflict = 0
    for i in range(graph.n):
        for j in range(i + 1, graph.n):
            if graph.W[i, j] > 0:          # conflict edge
                n_conflict += 1
                if result.partition[i] * result.partition[j] < 0:
                    n_correct += 1
    print(f"\n  Conflict-edge separation: {n_correct}/{n_conflict} "
          f"conflicting pairs in different slots")
    gate = n_conflict == 0 or n_correct / n_conflict >= 0.75
    print(f"  Calendar gate: {'PASS' if gate else 'FAIL'}")
    return gate


def run_genetics():
    print("\n══ GENETICS ADAPTER ══════════════════════════════════════════════")
    graph, truth, positions = simulate_diploid(
        n_snps=200, coverage=15, read_len=15, error_rate=0.02, seed=0
    )
    print(graph.summary())

    solver = WindingSolver(steps=2000, restarts=24, init="auto")
    result = solver.solve(graph)

    pred_b = (result.partition > 0).astype(int)
    h = np.mean(pred_b != truth)
    acc = 1.0 - min(h, 1.0 - h)

    print(f"\n  Accuracy      : {acc:.4f}  (Phase 1 read_len=8 baseline: 0.59)")
    print(f"  Vortex count  : {result.vortex_count}")
    print(f"  Cut value     : {result.cut_value:.1f}")
    print(f"  Runtime       : {result.runtime:.2f}s")

    print("\n  Tension map (genomic windows):")
    for lo, hi, t in result.tension_map:
        bar = "█" * int(15 * t / (max(x[2] for x in result.tension_map) + 1e-9))
        print(f"    SNP {lo:>10} – {hi:>10}  {t:.3f}  {bar}")

    gate = acc >= 0.75
    print(f"\n  Genetics gate: {'PASS (acc ≥ 0.75)' if gate else f'FAIL (acc={acc:.3f})'}")
    return gate


if __name__ == "__main__":
    cal_ok = run_calendar()
    gen_ok = run_genetics()

    print("\n══ PHASE 2 GATE ══════════════════════════════════════════════════")
    print(f"  Calendar : {'PASS' if cal_ok else 'FAIL'}")
    print(f"  Genetics : {'PASS' if gen_ok else 'FAIL'}")
    overall = cal_ok and gen_ok
    print(f"  Overall  : {'PASS — engine/core is ready' if overall else 'FAIL — see above'}")
