"""
Hum — recurring-structure coherence engine  v0.1
════════════════════════════════════════════════════════════════════════════
Point it at one or more .ics calendar files. It:
  1. parses events (zero dependencies — minimal RFC-5545 reader)
  2. keeps only RECURRING commitments (the skeleton; one-offs are ignored)
  3. normalizes each to a phase on its natural cycle (weekly / daily)
  4. builds couplings (overlap = repulsion, adjacency-without-buffer = strain)
  5. settles the phase field (phase-oscillator settling heuristic, sin coupling)
  6. reports a coherence score R̄ and a ranked TENSION MAP

The test this is built FOR: does the tension map surface conflicts you did
NOT already know about? If yes, it reduces real cognitive friction. If it only
echoes what you can already see, it's a toy. Run it on your own calendar and
judge honestly.

Engine split honored: this file is the DETERMINISTIC core + the COHERENCE
heuristic. No language model, no field LM, nothing probabilistic about times.
The solver is used only to score/rank structural tension — never to move a
meeting on its own.

Usage:
    python hum_engine.py mycal.ics
    python hum_engine.py work.ics personal.ics
    python hum_engine.py --demo          # runs on a synthetic calendar
════════════════════════════════════════════════════════════════════════════
"""
import sys
import re
import math
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# 1. Minimal .ics reader  (handles the common subset: VEVENT, DTSTART/DTEND,
#    RRULE with FREQ/BYDAY/INTERVAL, SUMMARY. Unfolds long lines per RFC 5545.)
# ─────────────────────────────────────────────────────────────────────────────


def _unfold(text):
    # RFC 5545: a CRLF followed by space/tab continues the previous line
    return re.sub(r'\r?\n[ \t]', '', text)


def _parse_dt(val):
    val = val.strip()
    # forms: 20260615T090000Z, 20260615T090000, 20260615
    m = re.match(
        r'(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?', val
    )
    if not m:
        return None, False
    y, mo, d, hh, mm, ss, z = m.groups()
    if hh is None:
        return datetime(int(y), int(mo), int(d)), True   # all-day
    return datetime(
        int(y), int(mo), int(d), int(hh), int(mm), int(ss or 0)
    ), False


def parse_ics(text):
    text = _unfold(text)
    events = []
    for block in re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', text, re.S):
        ev = {'summary': '(untitled)', 'rrule': None, 'dtstart': None,
              'dtend': None, 'allday': False}
        for line in block.splitlines():
            line = line.strip()
            if not line or ':' not in line:
                continue
            key, val = line.split(':', 1)
            key = key.split(';')[0].upper()
            if key == 'SUMMARY':
                ev['summary'] = val.strip()
            elif key == 'DTSTART':
                ev['dtstart'], ev['allday'] = _parse_dt(val)
            elif key == 'DTEND':
                ev['dtend'], _ = _parse_dt(val)
            elif key == 'RRULE':
                ev['rrule'] = val.strip()
        if ev['dtstart']:
            if ev['dtend'] and not ev['allday']:
                ev['duration'] = (
                    (ev['dtend'] - ev['dtstart']).total_seconds() / 3600.0
                )
            else:
                ev['duration'] = 1.0
            events.append(ev)
    return events


def parse_rrule(rrule):
    if not rrule:
        return None
    d = {}
    for part in rrule.split(';'):
        if '=' in part:
            k, v = part.split('=', 1)
            d[k.upper()] = v
    return d


# ─────────────────────────────────────────────────────────────────────────────
# 2. Keep recurring commitments; normalize to a phase on a cycle
#    Weekly commitments → phase on the 7-day week (the dominant exec cycle).
#    Daily commitments  → phase on the 24-hour day.
# ─────────────────────────────────────────────────────────────────────────────
DAYMAP = {'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5, 'SU': 6}
WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def to_commitments(events):
    """Return list of recurring commitments with a (cycle, phase, duration)."""
    out = []
    for ev in events:
        rr = parse_rrule(ev['rrule'])
        if not rr:                      # one-off: not part of the skeleton
            continue
        freq = rr.get('FREQ', '').upper()
        dt = ev['dtstart']
        hour = dt.hour + dt.minute / 60.0
        if freq == 'WEEKLY':
            days = [
                DAYMAP[d] for d in rr.get('BYDAY', '').split(',')
                if d in DAYMAP
            ]
            if not days:
                days = [dt.weekday()]
            interval = int(rr.get('INTERVAL', 1))
            for wd in days:
                # phase in [0,2π): position = day + fraction of day
                frac = (wd + hour / 24.0) / 7.0
                out.append({
                    'summary': ev['summary'], 'cycle': 'week',
                    'phase': 2 * math.pi * frac, 'duration': ev['duration'],
                    'weekday': wd, 'hour': hour, 'interval': interval,
                    'span_hours': ev['duration'],
                })
        elif freq == 'DAILY':
            frac = hour / 24.0
            out.append({
                'summary': ev['summary'], 'cycle': 'day',
                'phase': 2 * math.pi * frac, 'duration': ev['duration'],
                'weekday': None, 'hour': hour,
                'interval': int(rr.get('INTERVAL', 1)),
                'span_hours': ev['duration'],
            })
        # monthly/yearly: lower-frequency skeleton, handled in a later version
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 3. Couplings.  Two recurring commitments on the same cycle interact when
#    their occupied time-windows are close on that cycle.
#      overlap            → strong repulsion (they literally collide)
#      gap < BUFFER hours  → mild strain (no recovery/transition time)
#    Weekly commitments only couple to weekly; daily to daily (v0.1).
# ─────────────────────────────────────────────────────────────────────────────
BUFFER_HOURS = 0.5     # desired minimum gap between back-to-back commitments


def cycle_hours(cycle):
    return 24.0 * 7 if cycle == 'week' else 24.0


def window(c):
    """Start position in hours on the cycle, and end."""
    if c['cycle'] == 'week':
        start = c['weekday'] * 24.0 + c['hour']
    else:
        start = c['hour']
    return start, start + c['span_hours']


def circ_gap(a_end, b_start, total):
    """Forward gap from a_end to b_start on a circle of length total."""
    g = (b_start - a_end) % total
    return g


def build_couplings(commits):
    """Return (W matrix, list of (i,j,kind,detail)) for same-cycle pairs."""
    n = len(commits)
    W = [[0.0] * n for _ in range(n)]
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            ci, cj = commits[i], commits[j]
            if ci['cycle'] == cj['cycle']:
                total = cycle_hours(ci['cycle'])
                si, ei = window(ci)
                sj, ej = window(cj)
                # overlap test on the circle: do [si,ei) and [sj,ej) intersect?
                gap_ij = circ_gap(ei, sj, total)   # i then j
                gap_ji = circ_gap(ej, si, total)   # j then i
                ov = circles_overlap(si, ei, sj, ej, total)
                min_gap = min(gap_ij, gap_ji)
                if ov:
                    w = 1.0
                    # bi-weekly that alternate may not actually collide
                    if ci['interval'] != cj['interval'] or ci['interval'] > 1:
                        detail = "overlap (check alternation — different cadence)"
                        w = 0.6
                    else:
                        detail = "direct overlap"
                    W[i][j] = W[j][i] = w
                    edges.append((i, j, 'overlap', detail, min_gap))
                elif min_gap < BUFFER_HOURS:
                    w = 0.4
                    W[i][j] = W[j][i] = w
                    edges.append((
                        i, j, 'tight',
                        f"only {min_gap * 60:.0f} min between them", min_gap
                    ))
            elif {ci['cycle'], cj['cycle']} == {'day', 'week'}:
                # cross-cycle: a DAILY commitment recurs every day, so it lands
                # on the weekly commitment's weekday too. Compare their
                # time-of-day windows on the 24-hour circle. (Previously these
                # pairs were skipped — a whole class of buried conflicts.)
                weekly = ci if ci['cycle'] == 'week' else cj
                sd = ci['hour']; ed = sd + ci['span_hours']
                se = cj['hour']; ee = se + cj['span_hours']
                ov = circles_overlap(sd, ed, se, ee, 24.0)
                min_gap = min(circ_gap(ed % 24, se % 24, 24.0),
                              circ_gap(ee % 24, sd % 24, 24.0))
                wd = WEEKDAYS[weekly['weekday']]
                if ov:
                    W[i][j] = W[j][i] = 1.0
                    edges.append((i, j, 'overlap',
                                  f"daily commitment lands on the {wd} slot",
                                  min_gap))
                elif min_gap < BUFFER_HOURS:
                    W[i][j] = W[j][i] = 0.4
                    edges.append((i, j, 'tight',
                                  f"only {min_gap * 60:.0f} min around the {wd} slot",
                                  min_gap))
    return W, edges


def circles_overlap(s1, e1, s2, e2, total):
    """Two arcs [s1,e1) and [s2,e2) on a circle of length total overlap?"""
    s1 %= total
    s2 %= total

    def slots(s, span):
        out = set()
        k = 0.0
        while k < span:
            out.add(round(((s + k) % total) * 4) / 4)  # 15-min grid
            k += 0.25
        return out

    sp1 = e1 - s1
    sp2 = e2 - s2
    return len(slots(s1, sp1) & slots(s2, sp2)) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. The coherence engine (oscillator-settling heuristic; see the correction
#    note in hum-scheduler-spec-v1.md -- the settling was measured to contribute
#    -0.19% over classical post-processing, so this is a tension heuristic, not a
#    benchmarked optimiser).
#    Phases evolve under repulsive coupling; we read:
#      R̄  = order parameter of the RESIDUAL frustration (how much tension
#            the structure can't resolve) → mapped to a 0..1 coherence score
#      per-commitment residual force = how stuck each commitment is
#    NOTE: we do NOT move real meetings. The solver measures whether the
#    coupling graph is satisfiable and where it strains. Phases are free to
#    relax in simulation to reveal structural tension; the real calendar is
#    untouched.
# ─────────────────────────────────────────────────────────────────────────────
def _strain_at(commits, W):
    """Total coupling strain at ACTUAL positions, and per-commitment strain.

    Strain of an edge = weight (overlap=strong, tight=mild): real present
    tension in the schedule as it actually stands.
    """
    n = len(commits)
    per = [0.0] * n
    total = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            if W[i][j] != 0.0:
                per[i] += W[i][j]
                per[j] += W[i][j]
                total += W[i][j]
    return total, per


def coherence(commits, W, edges, steps=1500, dt=0.05, seed=0):
    """
    Two distinct readouts:
      R̄ (coherence) = tension in the ACTUAL recurring schedule, mapped to
                       0..1. Driven by real overlaps/tight gaps, NOT by
                       whether a hypothetical rearrangement exists.
      satisfiable    = does a conflict-free arrangement exist at all? Phases
                       relax under repulsion; if residual strain can reach ~0
                       the schedule is satisfiable, otherwise OVERCOMMITTED.
    """
    n = len(commits)
    if n == 0:
        return 1.0, [], True

    # ── 1. coherence from ACTUAL strain (fixes the R̄=1-with-collisions bug)
    total_strain, per = _strain_at(commits, W)
    R = math.exp(-total_strain / max(n, 1))    # more real conflict → lower R̄

    # ── 2. satisfiability probe: can repulsion resolve everything?
    th = [c['phase'] for c in commits]
    for step in range(steps):
        damp = 1.0 - step / steps
        newth = th[:]
        for i in range(n):
            f = 0.0
            for j in range(n):
                if W[i][j] != 0.0:
                    f += W[i][j] * math.sin(th[i] - th[j])
            newth[i] = (th[i] + dt * f * damp) % (2 * math.pi)
        th = newth
    # measure residual collisions after relaxation by re-deriving windows
    # from relaxed phases on the same cycle
    relaxed_conflicts = 0
    for (i, j, kind, detail, gap) in edges:
        ci, cj = commits[i], commits[j]
        if ci['cycle'] == cj['cycle']:
            total = cycle_hours(ci['cycle'])
            sh_i = (th[i] / (2 * math.pi)) * total
            sh_j = (th[j] / (2 * math.pi)) * total
            if circles_overlap(sh_i, sh_i + ci['span_hours'],
                               sh_j, sh_j + cj['span_hours'], total):
                relaxed_conflicts += 1
        else:  # cross-cycle day/week: compare time-of-day on the 24h circle
            hi = ((th[i] / (2 * math.pi)) * cycle_hours(ci['cycle'])) % 24
            hj = ((th[j] / (2 * math.pi)) * cycle_hours(cj['cycle'])) % 24
            if circles_overlap(hi, hi + ci['span_hours'],
                               hj, hj + cj['span_hours'], 24.0):
                relaxed_conflicts += 1
    satisfiable = (relaxed_conflicts == 0)

    ranked = sorted(range(n), key=lambda i: -per[i])
    return R, [(i, per[i]) for i in ranked if per[i] > 0], satisfiable


# ─────────────────────────────────────────────────────────────────────────────
# 5. Report
# ─────────────────────────────────────────────────────────────────────────────
WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def fmt(c):
    if c['cycle'] == 'week':
        h = int(c['hour'])
        m = int((c['hour'] % 1) * 60)
        return f"{WD[c['weekday']]} {h:02d}:{m:02d} · {c['summary']}"
    h = int(c['hour'])
    m = int((c['hour'] % 1) * 60)
    return f"daily {h:02d}:{m:02d} · {c['summary']}"


def report(commits, W, edges, R, ranked, satisfiable):
    print("=" * 68)
    print("  HUM — recurring-structure coherence")
    print("=" * 68)
    print(f"\n  Recurring commitments analyzed: {len(commits)}")
    print(f"  Coherence score R̄ = {R:.3f}   ", end="")
    if R > 0.85:
        print("(humming — structure holds together)")
    elif R > 0.6:
        print("(some strain)")
    else:
        print("(structurally overcommitted)")

    if edges and not satisfiable:
        print("  ⚑ OVERCOMMITTED: no conflict-free arrangement of these")
        print("    recurring commitments exists — something must give.")
    elif edges and satisfiable:
        print("  ✓ Resolvable: a conflict-free arrangement DOES exist —")
        print("    these collisions are fixable by moving commitments.")

    if not edges:
        print("\n  No structural tensions found among recurring commitments.")
        print("  Either the skeleton is clean, or there aren't enough")
        print("  recurring events to collide. (One-offs are intentionally"
              " ignored.)")
        return

    print(f"\n  TENSION MAP  ({len(edges)} found, worst first):\n")
    edges_sorted = sorted(edges, key=lambda e: e[4])
    for (i, j, kind, detail, gap) in edges_sorted:
        tag = "⚠ COLLISION" if kind == 'overlap' else "· tight"
        print(f"  {tag}: {detail}")
        print(f"      {fmt(commits[i])}")
        print(f"      {fmt(commits[j])}\n")

    if ranked:
        print("  Most-frustrated commitments (most coupled to others):")
        for i, r in ranked[:5]:
            print(f"      [{r:4.2f}]  {fmt(commits[i])}")
    print("\n  (Collisions you already knew about = expected. The real")
    print("   test is whether any above are ones you HADN'T noticed.)")


# ─────────────────────────────────────────────────────────────────────────────
# Demo calendar — a plausibly messy executive week, with two BURIED conflicts
# ─────────────────────────────────────────────────────────────────────────────
DEMO = """BEGIN:VCALENDAR
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
BEGIN:VEVENT
SUMMARY:Ops review
DTSTART:20260616T081500
DTEND:20260616T084500
RRULE:FREQ=WEEKLY;BYDAY=TU
END:VEVENT
END:VCALENDAR"""


def main():
    args = [a for a in sys.argv[1:]]
    if not args or '--demo' in args:
        print(
            "(running on synthetic demo calendar"
            " — pass a .ics path to use yours)\n"
        )
        text = DEMO
        events = parse_ics(text)
    else:
        events = []
        for path in args:
            with open(path, 'r', errors='ignore') as f:
                events += parse_ics(f.read())
    commits = to_commitments(events)
    W, edges = build_couplings(commits)
    R, ranked, satisfiable = coherence(commits, W, edges)
    report(commits, W, edges, R, ranked, satisfiable)


if __name__ == "__main__":
    main()
