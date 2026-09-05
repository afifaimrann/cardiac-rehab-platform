# The clinical logic

The rules, thresholds and equations, with the source for each number.

[← back to the README](../README.md)

---


---

## The risk engine

Rules, not a model — a rehabilitation programme needs decisions a clinician can
read, audit and overrule, and every flag traces to a named threshold stored with
the flag. Tuning the thresholds later does not rewrite the history of flags
already raised.

| Rule | Trigger | Severity |
|---|---|---|
| `BP_HYPERTENSIVE_CRISIS` | ≥180/120 mmHg | severe |
| `BP_HIGH` | ≥160/100 mmHg | moderate |
| `BP_LOW` | systolic ≤90 mmHg | moderate |
| `HR_ABOVE_TARGET` | above the patient's prescribed ceiling | moderate / severe |
| `HR_LOW` | <45 bpm | moderate |
| `SPO2_LOW` / `SPO2_BORDERLINE` | <90% / <94% | severe / mild |
| `SYMPTOM_RED_FLAG` | cardiac red-flag keywords | moderate / severe |
| `SYMPTOM_SEVERE` | patient rates a symptom severe | moderate |
| `EXERTION_HIGH` | Borg RPE ≥17 | moderate |
| `SESSION_ABANDONED` | session logged incomplete | mild |

Two details that matter in use:

- **Thresholds are personalised where a baseline exists.** A heart rate of 115
  is unremarkable by default but flags for a patient whose prescribed ceiling is
  110.
- **Overlapping rules are suppressed.** A 190/125 reading raises one crisis flag,
  not a crisis flag *and* a high-BP flag. A queue that double-reports trains
  clinicians to ignore it.

Adding a rule means adding one function to the relevant tuple. Nothing else
changes.

---

## The six-minute walk test

The 6MWT is the standard submaximal measure of functional capacity in cardiac
rehabilitation: distance walked on a flat course in six minutes, with heart
rate, oxygen saturation and perceived exertion before and after. `screen()`
separates absolute contraindications (which block the test) from relative ones
(which require supervision), because collapsing the two would either forbid
safe tests or permit unsafe ones. Predicted distance uses the Enright &
Sherrill equations and returns `None` rather than a guess when height, weight,
age or sex is missing — a percentage of a predicted distance computed from an
assumed height is a number that looks clinical and means nothing.

### Cutting the manual input

The first version of this screen asked for roughly fifteen numbers, four
checkboxes and four Borg ratings across four stages, then asked for the rests
and the lowest SpO₂ from memory once the patient had sat down. Almost none of
that had to be typed:

| Was typed | Now |
|---|---|
| Resting HR, systolic, diastolic at screening | Offered from the last reading, with its age, if it is under 90 minutes old |
| The same three again as baseline | Carried through from the screening — it was the same measurement asked twice |
| Rests taken, seconds rested | A **Patient resting** button on the timer |
| Lowest SpO₂ during the walk | The minimum of the readings logged during the walk |
| SpO₂ at the end | The last reading logged, unless overridden |
| Four contraindication checkboxes | One line summarising the last test's answers, expandable if anything changed |
| Weight | From the most recent reading that carried one |
| Two baseline Borg ratings | Collapsed behind a link; optional by protocol |

What is left is what is genuinely new on the day: baseline SpO₂, post-walk heart
rate and SpO₂, and the two post-walk Borg ratings.

Two decisions in there are deliberately conservative. A reading older than
`VITALS_STALE_AFTER` (90 minutes) is shown but **not** pre-filled, because a
resting heart rate carried over from yesterday is not a pre-test observation and
must not clear a patient with one tap. And a previous test with no stored
screening answers offers nothing back rather than defaulting to all-false —
inventing "no contraindications" from an absence would clear a patient nobody
screened.

---

## Scheduling and video consultations

The clinician publishes a weekly rota; patients book themselves. There is no
request-and-approve step, because the back-and-forth of arranging a time is
precisely the part that does not need a person.

**The rota is rules, not rows.** `AvailabilityRule` stores "Tuesdays, 09:00 to
13:00, thirty-minute slots, video". Slots are generated on read by
`services/scheduling.py`. A clinic publishing twelve weeks of half-hour slots
would otherwise write four hundred rows that mostly go unused, and every rota
change would have to rewrite them.

**Double-booking is prevented in the database.** Two patients can post the same
slot in the same millisecond, so a check in the handler is not enough.
Appointments carry a `slot_key` (`clinician:20260908T0400`) under a unique
constraint; cancelling sets it to `NULL`, and NULLs do not collide under a
unique index on either SQLite or Postgres — so a cancelled time becomes bookable
again without needing a partial index.

**Timezones are converted in one place.** The rota is authored in clinic-local
wall-clock time and stored as a naive `time` against a weekday;
`CLINIC_TIMEZONE_OFFSET_MINUTES` converts. A scheduling bug that puts a
consultation six hours out is invisible in tests written in the same wrong
timezone as the code, so the tests assert on clinic-local time explicitly.

**Video rooms are Jitsi, and the room name is random.** Jitsi needs no account
or credentials, so booking produces a link that actually opens a call. The room
name comes from `secrets`, never from the appointment id, the patient, or the
date: a Jitsi room is created by whoever visits its URL first, and anyone who
knows the name can walk into the consultation. Cancelling clears the URL, so a
stale calendar invite cannot open a live room. Zoom and Google Meet sit behind
the same `create_room()` interface but need per-clinic OAuth credentials;
rather than fake a plausible-looking Zoom URL that dials nowhere, the service
raises and the API says the provider is not configured.
