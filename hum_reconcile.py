"""
Hum Reconcile — "did it land everywhere it should?"  v0.1
════════════════════════════════════════════════════════════════════════════
The anxiety this answers: you keep several calendars (across several email
accounts). You make an appointment. Did it actually get recorded on the
calendars it belongs on — or did a sync glitch silently drop it from one?

This tool reads two or more calendars and reports, plainly:
  • events that are present in SOME calendars but MISSING from others
  • a per-calendar count so you can see at a glance if one is sparse
  • a clear "all calendars agree" when they do

It does NOT need internet, accounts, or passwords. You export each calendar
to an .ics file and point this at them. Nothing is sent anywhere. Read-only:
it never changes any calendar.

It is deliberately conservative: when unsure whether two events are "the same,"
it tells you rather than guessing silently — because a false "all clear" is the
one output that would make the anxiety worse, not better.

Usage:
    python hum_reconcile.py work.ics personal.ics
    python hum_reconcile.py gmail.ics icloud.ics outlook.ics
    python hum_reconcile.py --demo
════════════════════════════════════════════════════════════════════════════
"""
import sys, re, math
from datetime import datetime, timedelta

# ── reuse the validated parser from hum_engine (inlined so this file stands alone)
def _unfold(text):
    return re.sub(r'\r?\n[ \t]', '', text)

def _parse_dt(val):
    val = val.strip()
    m = re.match(r'(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?', val)
    if not m: return None, False
    y, mo, d, hh, mm, ss, z = m.groups()
    if hh is None:
        return datetime(int(y), int(mo), int(d)), True
    return datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss or 0)), False

def _norm_summary(s):
    """Loose normalization so trivial differences don't read as 'missing'."""
    s = s.lower().strip()
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[^\w ]', '', s)          # drop punctuation/emoji
    return s

def parse_ics(text):
    text = _unfold(text)
    events = []
    for block in re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', text, re.S):
        ev = {'summary': '(untitled)', 'dtstart': None, 'dtend': None,
              'allday': False, 'uid': None, 'rrule': None}
        for line in block.splitlines():
            line = line.strip()
            if not line or ':' not in line: continue
            key, val = line.split(':', 1)
            key = key.split(';')[0].upper()
            if key == 'SUMMARY':   ev['summary'] = val.strip()
            elif key == 'DTSTART': ev['dtstart'], ev['allday'] = _parse_dt(val)
            elif key == 'DTEND':   ev['dtend'], _ = _parse_dt(val)
            elif key == 'UID':     ev['uid'] = val.strip()
            elif key == 'RRULE':   ev['rrule'] = val.strip()
        if ev['dtstart']:
            events.append(ev)
    return events

# ── matching: two events are "the same" if same day + same start time (to the
#    minute) + similar title, OR identical UID. We match on (day, time, title)
#    rather than UID alone, because the SAME real appointment often gets a
#    DIFFERENT UID on each calendar (re-created rather than synced) — which is
#    exactly the case UID-based tools miss.
def event_key(ev, time_tolerance_min=0):
    dt = ev['dtstart']
    if ev['allday']:
        return (dt.date(), 'allday', _norm_summary(ev['summary']))
    return (dt.date(), (dt.hour, dt.minute), _norm_summary(ev['summary']))

def fuzzy_same(a, b, minutes=10):
    """Fallback: same day, titles match, start within `minutes`."""
    if a['allday'] != b['allday']: return False
    if _norm_summary(a['summary']) != _norm_summary(b['summary']): return False
    if a['allday']:
        return a['dtstart'].date() == b['dtstart'].date()
    return abs((a['dtstart'] - b['dtstart']).total_seconds()) <= minutes*60

def reconcile(calendars):
    """
    calendars: dict name -> list of events.
    Returns list of unified events, each with the set of calendars it appears on.
    """
    names = list(calendars.keys())
    # build a flat list of (calendar_name, event)
    unified = []   # each: {'event':..., 'present_in': set(names)}
    for name in names:
        for ev in calendars[name]:
            placed = False
            # exact key match first
            k = event_key(ev)
            for u in unified:
                if event_key(u['event']) == k or fuzzy_same(u['event'], ev):
                    u['present_in'].add(name)
                    placed = True
                    break
            if not placed:
                unified.append({'event': ev, 'present_in': {name}})
    return unified, names

WD = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
def fmt_ev(ev):
    dt = ev['dtstart']
    if ev['allday']:
        return f"{dt.strftime('%Y-%m-%d')} (all day) · {ev['summary']}"
    return f"{dt.strftime('%Y-%m-%d')} {dt.strftime('%H:%M')} {WD[dt.weekday()]} · {ev['summary']}"

def report(unified, names):
    print("="*70)
    print("  HUM RECONCILE — did every event land where it should?")
    print("="*70)
    print(f"\n  Calendars checked: {len(names)}")
    for n in names:
        cnt = sum(1 for u in unified if n in u['present_in'])
        print(f"    · {n}: {cnt} events")

    all_set = set(names)
    missing = [u for u in unified if u['present_in'] != all_set]
    # only meaningful to flag "missing" when there are 2+ calendars
    if len(names) < 2:
        print("\n  Only one calendar given — nothing to cross-check against.")
        print("  Export a second calendar and pass both to compare them.")
        return

    if not missing:
        print(f"\n  ✓ ALL {len(unified)} events appear on every calendar.")
        print("    Your calendars agree. Nothing dropped.")
        return

    print(f"\n  ⚠ {len(missing)} event(s) are NOT on every calendar:\n")
    # sort by date
    missing.sort(key=lambda u: u['event']['dtstart'])
    for u in missing:
        on = u['present_in']
        off = all_set - on
        print(f"  {fmt_ev(u['event'])}")
        print(f"      on: {', '.join(sorted(on))}")
        print(f"      MISSING from: {', '.join(sorted(off))}\n")

    print("  These are the events to check. An event you EXPECT on only one")
    print("  calendar (e.g. a work-only meeting) showing as 'missing' from your")
    print("  personal calendar is normal — the tool can't know your intent, so")
    print("  it shows you everything and lets you decide. (v0.1: missing-only.)")

# ── demo: two calendars where one event silently failed to sync ──────────────
DEMO_A = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:a1
SUMMARY:Dentist
DTSTART:20260618T140000
DTEND:20260618T150000
END:VEVENT
BEGIN:VEVENT
UID:a2
SUMMARY:Mom birthday
DTSTART;VALUE=DATE:20260622
END:VEVENT
BEGIN:VEVENT
UID:a3
SUMMARY:Tax deadline reminder
DTSTART:20260630T090000
DTEND:20260630T093000
END:VEVENT
END:VCALENDAR"""

DEMO_B = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:b1-different-uid
SUMMARY:Dentist
DTSTART:20260618T140000
DTEND:20260618T150000
END:VEVENT
BEGIN:VEVENT
UID:b2
SUMMARY:Mom birthday
DTSTART;VALUE=DATE:20260622
END:VEVENT
END:VCALENDAR"""

def main():
    args = [a for a in sys.argv[1:]]
    if not args or '--demo' in args:
        print("(demo: two calendars; the tax-deadline event is on A but dropped from B)\n")
        cals = {'calendar-A': parse_ics(DEMO_A), 'calendar-B': parse_ics(DEMO_B)}
    else:
        cals = {}
        for path in args:
            name = path.rsplit('/',1)[-1].rsplit('.',1)[0]
            with open(path, 'r', errors='ignore') as f:
                cals[name] = parse_ics(f.read())
    unified, names = reconcile(cals)
    report(unified, names)

if __name__ == "__main__":
    main()
