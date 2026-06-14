# Hum — Scheduler Companion Spec v1
## A recurring-structure layer that sits beside Motion (and any calendar tool)

*Working name: Hum. Category search shows no scheduling product using it; final
wordmark pending an app-store exact-match and USPTO/TESS check before launch.*

---

## 0. One-paragraph definition

Coherence is not a scheduler. It is the layer the schedulers lack: it reasons
about the *recurring skeleton* of an executive's calendar — standing meetings,
board cadence, market-hours constraints, the rotation of regular commitments
across time zones — as a coupled-oscillator system, and tells you how much
structural tension that skeleton carries and exactly where. Motion, Reclaim, and
Clockwise optimize a *list* (tasks, habits, meeting placement). Coherence reads
the calendar they already produce and answers a question none of them ask: **is
the periodic shape of my life stable, and where will it break?**

It complements rather than replaces. You keep Motion. Coherence makes Motion's
output legible and surfaces the structural conflicts no task-scheduler sees.

---

## 1. The honest engine split (the spine of the whole product)

Three engines. Each does only what it is correct for. This separation is a
product-integrity commitment, not an implementation detail, and it is stated
plainly in the product itself.

1. **Deterministic calendar core.** Anything involving exact times, dates,
   recurrence expansion, time-zone conversion, conflict detection, running
   counts. Plain, auditable arithmetic. Never probabilistic. If Coherence ever
   tells you a meeting is at 3:00, it is at 3:00.
2. **The coherence engine (the validated TFT solver).** The phase-oscillator
   settling dynamics — the one capability that survived benchmarking against
   simulated annealing. Used *only* for what it is native to: measuring
   structural tension in cyclic commitments and running "what-if" re-settling.
   It never moves a meeting on its own; it scores and reveals.
3. **TeotlAGI — not present at launch.** No field language model anywhere near
   scheduling decisions until it has passed a measured capability gate. When/if
   it earns a place, its only candidate role is natural-language input
   ("move my standing 1:1 earlier on Fridays") behind an explicit confirmation
   step, degrading gracefully to manual entry. Until then: omitted entirely.

**Marketing honesty rule (borrowed from the category leader):** Reclaim openly
advertises "constraint-based algorithms, not generative AI" as a *trust*
feature. Coherence does the same — the coherence engine is deterministic
oscillator dynamics, fully explainable, on-device. We never call it "AI" to
borrow shine it doesn't need.

---

## 2. The integration insight — improve many tools via one layer

Do **not** integrate Motion's API, then Reclaim's, then Clockwise's. Instead,
read the **calendar substrate they all write to** (Google Calendar + Microsoft
Graph/Outlook). Whatever Motion schedules lands on Google Calendar; Coherence
reads it there. This means:

- One integration (two calendar providers) covers *every* scheduler the user
  runs, present and future, including manual scheduling and tools that don't
  exist yet.
- Coherence is automatically compatible with stacked setups (the reviews show
  people run Reclaim + Calendly + Motion together).
- Write-back is optional and scoped: Coherence proposes; the user's existing
  tool or the user executes. Coherence's default posture is read-and-reveal,
  not write-and-reshuffle — directly addressing the documented complaint that
  Motion's silent rearranging is "anxiety-inducing."

**Access tiers:** read-only (analysis only, safest default) → suggest (writes
proposals to a separate visible calendar the user accepts/rejects) → managed
(writes accepted changes back). User chooses; starts at read-only.

---

## 3. Core model — what "recurring coherence" actually means

The deterministic core expands all events into a normalized representation:
each commitment has a period (daily/weekly/monthly/quarterly), a phase
(position within its cycle), a duration, a flexibility (fixed vs movable), and
coupling relations to other commitments (must-not-overlap, should-align,
should-separate, same-prep-block).

The coherence engine maps this to its native form: each recurring commitment is
a phase oscillator on the appropriate cycle; couplings are the solver's edge
weights (repulsive for must-not-overlap, attractive for should-align). The field
settles. Two readouts come directly out of the validated solver:

- **Coherence score R̄** — the order parameter, in [0,1]. High = the recurring
  structure is internally consistent and stable. Low = chronic structural
  conflict. This is the same R̄ the MAX-CUT benchmark used; here it measures
  schedule health.
- **Tension map** — per-commitment residual: which oscillators *won't* settle.
  A commitment that stays frustrated is a constraint that cannot be satisfied
  given the others. These are surfaced as named conflicts for human judgment —
  the machine settles what it can and hands you the genuine dilemmas.

**Why this is honest:** the solver loses to tuned SA by a few percent on hard
random graphs (we measured it). But schedule-coupling graphs are small,
structured, and sparse — exactly the regime where it found optima exactly. The
problem size is tens of recurring commitments, not thousands of vertices. It
runs in milliseconds on a phone CPU, which is what makes the live-settling
visualization and full on-device operation possible.

---

## 4. High-end functionality (the executive tier)

1. **The Coherence Dashboard.** One number (R̄) and a ranked tension list.
   "Your recurring structure is 0.78 coherent. Two chronic conflicts: the
   Tuesday board prep collides with the EMEA standup every third week; your
   Friday 1:1 block has no recovery gap before the exec sync." Pure solver
   output, legible, no black box.
2. **Multi-zone phase alignment.** Coordinating recurring commitments across a
   global team is *literally* coupled-oscillators-on-a-circle — the most native
   case for the engine and the weakest spot for every competitor. Find the
   standing-meeting phase that minimizes total pain across time zones; show the
   tradeoff, don't impose it.
3. **What-if re-settling.** Add or move a *recurring* commitment; watch the
   field re-settle live; see what goes tense before you commit. The
   visualization is the differentiator — optimization you can watch, the
   opposite of Motion's silent reshuffle.
4. **Cadence scenarios.** Rank candidate meeting rhythms (weekly vs biweekly,
   morning vs afternoon standing slots) by resulting coherence and by tension
   introduced elsewhere.
5. **Erosion alert.** As the real calendar drifts week to week, R̄ trends.
   A falling coherence trend warns that the recurring structure is degrading
   before it becomes a crisis — a leading indicator no list-scheduler provides.
6. **Local-first / on-device.** The engine runs locally; calendar data need not
   transit a server for analysis. For executives this is a genuine
   privacy/security posture the cloud incumbents structurally cannot match, and
   it inherits the project's standing rule: any data protection uses vetted
   cryptography, never anything experimental.

---

## 5. Interface principles (minimalist, device-neutral)

- **One primary surface:** the calendar-as-cycle view, zoomable from a single
  week out to the recurring year, with tension shown as visual heat, not text
  walls. Default view answers "where does it hurt" in one glance.
- **Device-neutral by construction:** the deterministic core + solver are a
  small portable compute layer (target: a single well-tested module compilable
  to run on web, iOS, Android, desktop). No heavy runtime. The UI is thin over
  a fast local engine.
- **Quiet by default.** No constant notifications, no streaks, no
  engagement-maximizing loops (the same anti-engagement stance from the Olin
  design — a tool for busy people must be one they can ignore safely and check
  on their terms).
- **Three taps to value:** connect calendar → see coherence score and top
  tensions → tap a tension to see the what-if. Everything past that is optional
  depth.

---

## 6. What Coherence is NOT (printed, honored)

1. Not a task scheduler. It does not replace Motion/Reclaim/Clockwise; it reads
   their output and adds the recurring-structure layer they lack.
2. Not generative AI. The coherence engine is deterministic oscillator
   dynamics, explainable end to end.
3. Not an autopilot. Default posture is reveal, not rearrange. The human makes
   the judgment calls the machine surfaces.
4. Not financial/legal/medical anything. Pure scheduling structure.

---

## 7. Build order

1. **Validate the pain first (no code).** A handful of conversations with
   executives and EAs: is "recurring-structure tension" a distinct felt problem,
   or a shrug inside Motion? Build nothing until this is a yes. Cheapest
   possible insurance.
2. Deterministic core: calendar read (Google first), recurrence normalization,
   coupling extraction, conflict detection. Useful on its own.
3. Coherence engine: adapt the validated solver (`maxcut_tft.py` lineage) to the
   scheduling coupling model; R̄ readout; tension map.
4. The dashboard + the zoomable cycle view + live what-if settling.
5. Outlook/Graph provider; multi-zone alignment.
6. Suggest/managed write-back tiers.
7. (Gated, later) TeotlAGI natural-language input, behind confirmation.

---

## 8. One-line positioning

**Hum: the layer that tells you whether the recurring shape of your calendar
holds together — and shows you exactly where it doesn't. Works beside the
scheduler you already use.**

*Note: "coherence" survives throughout as the name of the engine's core
readout (the order parameter R̄) — so the product is Hum, and what it measures
is your schedule's coherence. The two names reinforce each other.*
