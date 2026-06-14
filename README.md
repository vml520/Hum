# Hum

**Calendar clarity. Runs entirely on your computer. Nothing is ever uploaded.**

Hum reads your calendar files (`.ics`) and helps you see them clearly: real
conflicts across your whole schedule, duplicate entries, stale clutter, and
whether calendars that should match actually do. It never changes your
original files — cleaned and archived calendars are saved as *new* files you
review before importing.

It is one HTML file. No installation, no account, no internet connection, no
server. Double-click it and it opens in your browser. Your calendar data never
leaves the page.

---

## Why Hum exists

Most calendar tools help you *schedule*. Hum helps you *trust what's already
there*. It was built for people who feel calendar clutter and uncertainty as a
real weight — who want to know, definitively, that nothing collided, nothing
was dropped, and nothing old is still hanging around. Every function produces a
short, finite list you can act on and finish, not an open-ended feed.

---

## What it does

Five functions, each working only on the calendar files you load:

1. **Conflicts** — pools *all* your calendars into one schedule and finds real
   time-vs-time clashes, including ones that span calendars (a family
   commitment landing on a work shift). Birthdays and all-day markers are
   excluded so they can't bury the real conflicts.
2. **Duplicates** — finds events entered more than once (exact copies collapse
   automatically; near-identical ones you confirm) and saves a cleaned copy.
3. **Clear clutter** — finds *stale* events (past appointments, ended class
   series) and lets you archive them one at a time or all at once. Removed
   events are saved to a separate archive file you can re-import anytime.
4. **Missing** — for calendars that should mirror each other, shows events
   present on some but missing from others (matched even when their internal
   IDs differ — the case that catches silent sync failures).
5. **Coherence** — a single score for how much structural tension your active
   recurring commitments carry. 1.00 means everything fits.

---

## How to use it

1. **Get the file.** Download `hum.html` from this repository
   (green **Code** button → **Download ZIP**, or download the single file).
2. **Open it.** Double-click `hum.html`. It opens in your default browser.
   (No internet needed — you can even open it offline.)
3. **Export your calendar** as `.ics`:
   - **Google Calendar:** Settings → Import & Export → Export
   - **Apple Calendar:** File → Export → Export
   - **Outlook:** File → Save Calendar (or export from the web app)
4. **Drag the `.ics` files** onto Hum, or click *Choose files*. Add two or more
   to compare them.
5. **Pick a function** from the tabs and read the results.

When you clean or archive, Hum downloads new files (e.g. `Home_cleaned.ics`,
`Home_archive.ics`). Your original is untouched. To use a cleaned calendar,
import the new file into a fresh calendar, or clear the old calendar's events
and import it.

---

## Your data stays yours

- Hum runs **100% in your browser.** There is no server and no network request.
- Your calendar files are read into the page's memory and discarded when you
  close the tab.
- Hum **never modifies your original files.** It only ever reads them and, when
  you ask, writes *new* files via your browser's download.
- Stale events are **never deleted without a backup** — everything removed is
  written to an archive file first.

You can verify all of this: the entire program is in `hum.html`, readable top
to bottom. There is nothing else.

---

## Repository contents

```
hum.html                  The app — one self-contained file. This is all you need.
tools/                    The original Python command-line versions (reference
                          implementation; same logic, for scripting/automation).
  hum_combined.py           cross-calendar conflicts
  hum_clean.py              duplicate finder + cleaner
  hum_archive.py            stale-event archiver
  hum_reconcile.py          missing-event checker
  hum_engine.py             coherence score
LICENSE                   MIT
README.md                 this file
```

The Python tools are optional. They do the same things from the command line if
you prefer scripting (e.g. `python tools/hum_combined.py Home.ics Family.ics`).
The HTML app is the recommended way to use Hum and needs nothing installed.

---

## Limitations (honest list)

- Recurring events are understood at the **weekly and daily** level. Monthly and
  quarterly recurrence (e.g. a board meeting every third Tuesday) is not yet
  analyzed for conflicts.
- Conflict detection compares **time-blocking** events. What counts as a
  "marker" (birthday, anniversary, all-day, reminder) is keyword-based and may
  miss an unusual label — if something is wrongly treated as a conflict or
  ignored, it's likely a marker-keyword gap.
- Timezone handling uses the time as written in the file; it does not convert
  between zones. For most personal calendars this is correct.
- Hum reads a common subset of the iCalendar format that covers ordinary
  personal and work calendars. Very unusual `.ics` features may not be modeled.

These are areas open for contribution.

---

## Contributing

Issues and pull requests are welcome — especially: replication of the behavior
on real calendars, additional marker keywords, monthly/quarterly recurrence,
and timezone handling. Bug reports that include a small sample `.ics`
(with private details removed) are the most useful kind.

---

## License

MIT — see [LICENSE](LICENSE). Free to use, modify, and distribute.
