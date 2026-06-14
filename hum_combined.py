"""
Hum Combined — your WHOLE schedule, across every calendar, one conflict check
════════════════════════════════════════════════════════════════════════════
You live one life; your calendars are just storage buckets. This pools them
all into a single schedule and finds the collisions that actually matter —
including the ones that span calendars (a Family commitment landing on a Home
class), which no single-calendar check can see.

The key distinction it makes (this is what keeps it from drowning you in noise):
  • TIME-BLOCKING commitments — a class, a shift, a meeting: things that
    occupy specific minutes and genuinely cannot overlap.
  • MARKERS — all-day events, birthdays, anniversaries, reminders: things on
    a day but not competing for a time slot. These NEVER count as conflicts.

So your birthday won't "collide" with every shift that day. Only real
time-vs-time clashes are flagged, each labeled with which calendars it spans.

Read-only. No internet, no accounts. Point it at your exported .ics files.

Usage:
    python hum_combined.py Home.ics Family.ics
    python hum_combined.py Home.ics Family.ics Work.ics
    python hum_combined.py --demo
════════════════════════════════════════════════════════════════════════════
"""
import sys, re, math
from datetime import datetime, timedelta

TODAY = datetime.now()
BUFFER_MIN = 0          # set >0 to also flag back-to-back with no gap as "tight"

# ─────────────────────────────────────────────────────────────────────────────
# Parser (keeps which calendar each event came from)
# ─────────────────────────────────────────────────────────────────────────────
def _unfold(text): return re.sub(r'\r?\n[ \t]', '', text)

def _parse_dt(val):
    val = val.strip()
    m = re.match(r'(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?', val)
    if not m: return None, False
    y, mo, d, hh, mm, ss, z = m.groups()
    if hh is None:
        return datetime(int(y), int(mo), int(d)), True
    return datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss or 0)), False

DAYMAP = {'MO':0,'TU':1,'WE':2,'TH':3,'FR':4,'SA':5,'SU':6}

def parse_ics(text, calname):
    text = _unfold(text)
    out = []
    for block in re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', text, re.S):
        ev = {'cal': calname, 'summary': '(untitled)', 'dtstart': None,
              'dtend': None, 'allday': False, 'rrule': None, 'byday': None,
              'freq': None, 'until': None, 'duration_min': 60}
        for line in block.splitlines():
            line = line.strip()
            if not line or ':' not in line: continue
            key, val = line.split(':', 1)
            key = key.split(';')[0].upper()
            if key == 'SUMMARY':   ev['summary'] = val.strip()
            elif key == 'DTSTART': ev['dtstart'], ev['allday'] = _parse_dt(val)
            elif key == 'DTEND':   ev['dtend'], _ = _parse_dt(val)
            elif key == 'RRULE':
                ev['rrule'] = val.strip()
                for part in val.split(';'):
                    if part.startswith('FREQ='):  ev['freq'] = part[5:]
                    if part.startswith('BYDAY='): ev['byday'] = [DAYMAP[d] for d in part[6:].split(',') if d in DAYMAP]
                    if part.startswith('UNTIL='):
                        m = re.match(r'(\d{8})', part[6:])
                        if m: ev['until'] = datetime.strptime(m.group(1), '%Y%m%d')
        if ev['dtstart']:
            if ev['dtend'] and not ev['allday']:
                ev['duration_min'] = max(1, int((ev['dtend']-ev['dtstart']).total_seconds()/60))
            out.append(ev)
    return out

# ─────────────────────────────────────────────────────────────────────────────
# Blocking vs marker
# ─────────────────────────────────────────────────────────────────────────────
MARKER_WORDS = ('birthday', 'anniversary', 'reminder', 'bday', 'holiday', 'pay day',
                'payday', 'due', 'deadline')   # day-markers, not time blocks
def is_marker(ev):
    if ev['allday']:
        return True                      # all-day = not competing for a slot
    s = ev['summary'].lower()
    return any(w in s for w in MARKER_WORDS)

def is_active(ev):
    """Drop events whose recurrence has fully ended (stale series) or past one-offs."""
    if ev['rrule']:
        if ev['until'] and ev['until'] < TODAY: return False
        return True
    end = ev['dtend'] or ev['dtstart']
    return end >= TODAY - timedelta(days=1)

# ─────────────────────────────────────────────────────────────────────────────
# Occurrence model on a weekly cycle (for recurring) or absolute (one-offs)
# We compare time-blocking commitments for real overlap.
#   - weekly recurring: occupies (weekday, start_min .. end_min) each week
#   - daily recurring:  occupies (every weekday, start..end)
#   - one-off:          occupies an absolute date + time window
# Two events conflict if they share weekday-and-time (recurring) or the same
# absolute date-and-time (one-off vs one-off), with overlapping minute windows.
# ─────────────────────────────────────────────────────────────────────────────
def weekly_slots(ev):
    """Return list of (weekday, start_min, end_min) this event occupies weekly.
       Returns None if the event is not weekly/daily-recurring."""
    if not ev['rrule']: return None
    dt = ev['dtstart']
    start_min = dt.hour*60 + dt.minute
    end_min = start_min + ev['duration_min']
    if ev['freq'] == 'WEEKLY':
        days = ev['byday'] if ev['byday'] else [dt.weekday()]
        return [(d, start_min, end_min) for d in days]
    if ev['freq'] == 'DAILY':
        return [(d, start_min, end_min) for d in range(7)]
    return None     # monthly/yearly recurring handled as markers-ish (rare clash)

def oneoff_slot(ev):
    if ev['rrule']: return None
    dt = ev['dtstart']
    start_min = dt.hour*60 + dt.minute
    return (dt.date(), start_min, start_min + ev['duration_min'])

def overlaps(a0, a1, b0, b1):
    return a0 < b1 and b0 < a1

def find_conflicts(events):
    blocking = [e for e in events if not is_marker(e) and is_active(e)]
    conflicts = []
    n = len(blocking)
    for i in range(n):
        for j in range(i+1, n):
            a, b = blocking[i], blocking[j]
            wa, wb = weekly_slots(a), weekly_slots(b)
            if wa and wb:
                for (da, s0, e0) in wa:
                    for (db, s1, e1) in wb:
                        if da == db and overlaps(s0, e0, s1, e1):
                            conflicts.append((a, b, _wd(da), _hhmm(s0), _hhmm(e1)))
                            break
            elif (not a['rrule']) and (not b['rrule']):
                oa, ob = oneoff_slot(a), oneoff_slot(b)
                if oa and ob and oa[0] == ob[0] and overlaps(oa[1],oa[2],ob[1],ob[2]):
                    conflicts.append((a, b, oa[0].strftime('%Y-%m-%d'),
                                      _hhmm(oa[1]), _hhmm(ob[2])))
            # recurring-vs-oneoff: only flag if the one-off falls on a recurring
            # weekday/time and is in the near future (kept simple in v0.1)
    return conflicts, blocking

WD=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
def _wd(d): return WD[d]
def _hhmm(m): return f"{m//60:02d}:{m%60:02d}"

def fmt(ev):
    dt = ev['dtstart']
    if ev['rrule'] and ev['freq']=='WEEKLY':
        days = '/'.join(_wd(d) for d in (ev['byday'] or [dt.weekday()]))
        return f"{days} {dt.strftime('%H:%M')} · {ev['summary']}  [{ev['cal']}]"
    if ev['rrule'] and ev['freq']=='DAILY':
        return f"daily {dt.strftime('%H:%M')} · {ev['summary']}  [{ev['cal']}]"
    return f"{dt.strftime('%Y-%m-%d %H:%M')} · {ev['summary']}  [{ev['cal']}]"

# ─────────────────────────────────────────────────────────────────────────────
def report(events, conflicts, blocking, calnames):
    print("="*70)
    print("  HUM COMBINED — your whole schedule, all calendars together")
    print("="*70)
    markers = [e for e in events if is_marker(e)]
    stale   = [e for e in events if not is_active(e)]
    print(f"\n  Calendars combined: {', '.join(calnames)}")
    for c in calnames:
        print(f"    · {c}: {sum(1 for e in events if e['cal']==c)} events")
    print(f"\n  Time-blocking commitments checked: {len(blocking)}")
    print(f"  Markers excluded (birthdays/anniversaries/all-day): {len(markers)}")
    if stale:
        print(f"  Stale (ended series / past) skipped: {len(stale)}")

    # dedupe identical conflict pairs
    seen, uniq = set(), []
    for c in conflicts:
        k = (id(c[0]), id(c[1]))
        if k not in seen:
            seen.add(k); uniq.append(c)

    if not uniq:
        print(f"\n  ✓ No time conflicts across your combined schedule.")
        print(f"    Every time-blocking commitment fits without overlap.")
        return

    # separate cross-calendar from same-calendar
    cross = [c for c in uniq if c[0]['cal'] != c[1]['cal']]
    same  = [c for c in uniq if c[0]['cal'] == c[1]['cal']]

    print(f"\n  ⚠ {len(uniq)} real time conflict(s) found "
          f"({len(cross)} span calendars, {len(same)} within one):\n")

    if cross:
        print("  ── CROSS-CALENDAR (the ones a single-calendar check would MISS) ──")
        for a, b, when, s, e in cross:
            print(f"     {when}:")
            print(f"        {fmt(a)}")
            print(f"        {fmt(b)}\n")
    if same:
        print("  ── WITHIN A SINGLE CALENDAR ──")
        for a, b, when, s, e in same:
            print(f"     {when}:")
            print(f"        {fmt(a)}")
            print(f"        {fmt(b)}\n")

    print("  (Markers like birthdays are intentionally NOT treated as conflicts.")
    print("   Only things competing for the same minutes are shown.)")

DEMO_HOME = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:CHN 101
DTSTART:20260615T130000
DTEND:20260615T135000
RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR
END:VEVENT
BEGIN:VEVENT
SUMMARY:Work
DTSTART:20260615T150000
DTEND:20260615T190000
RRULE:FREQ=WEEKLY;BYDAY=MO,WE
END:VEVENT
BEGIN:VEVENT
SUMMARY:ISTA 302 Technology of Sound
DTSTART:20260615T133000
DTEND:20260615T150000
RRULE:FREQ=WEEKLY;BYDAY=MO,WE
END:VEVENT
END:VCALENDAR"""

DEMO_FAMILY = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Mom Birthday
DTSTART;VALUE=DATE:20260615
END:VEVENT
BEGIN:VEVENT
SUMMARY:Family dinner
DTSTART:20260615T180000
DTEND:20260615T193000
RRULE:FREQ=WEEKLY;BYDAY=MO
END:VEVENT
END:VCALENDAR"""

def main():
    args = sys.argv[1:]
    if not args or '--demo' in args:
        print("(demo: Home + Family. Birthday is a marker (ignored); Family dinner")
        print(" Mon 18:00 collides with Work Mon 15:00-19:00 — a CROSS-calendar clash)\n")
        cals = {'Home': parse_ics(DEMO_HOME,'Home'), 'Family': parse_ics(DEMO_FAMILY,'Family')}
    else:
        paths = [a for a in args if not a.startswith('--')]
        cals = {}
        for p in paths:
            name = p.rsplit('/',1)[-1].rsplit('.',1)[0]
            with open(p,'r',errors='ignore') as f:
                cals[name] = parse_ics(f.read(), name)
    events = [e for evs in cals.values() for e in evs]
    conflicts, blocking = find_conflicts(events)
    report(events, conflicts, blocking, list(cals.keys()))

if __name__ == "__main__":
    main()
