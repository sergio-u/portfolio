# Live routing pilot: Jev 1.13.0

Coverage now includes 30 distinct scenarios and 37 live calls: the initial
12 cases, 7 repeats plus 1 new case, and a later expansion of 17 fresh cases.
The revised prompt set was used for 25 distinct live cases (8 plus 17).
The current offline suite contains 63 passing checks.

## Initial 20-call pilot

The operator authorized live TypeSafe calls using synthetic examples. The pilot
used the actual extension source in a mocked Pi host and the real pi-typesafe
0.7.0 client. No coding model was invoked. Prior-task context was seeded with
explicit offline fixtures; expected labels were never sent to Jev. Most examples
expose all Pi effort labels; the image example exposes only low/medium/high.
These are synthetic capability sets, not validation of Astra's API support.

The ceiling was 20 HTTP submissions with no retries, a five-second request
limit, a 16 KiB payload cap, and a client spend ceiling of $0.05 above the existing
daily estimate. Existing environment-based daily caps remained effective.

One evaluation per example batched the effort and task-relationship questions.
Examples were evaluated sequentially in separate mocked sessions. Live calls
used the normal credential resolver and usage ledger; router consent and session
state were isolated in a temporary directory. No real routing preferences changed.

## Initial results

| Measure | Observation |
| --- | --- |
| Returned model | `jev-1.13.0` on all 20 requests |
| Baseline | 12 examples; selected effort and relationship labels were within all predeclared ranges; applied effort was within range on 8/12 |
| Revised follow-up | 7 repeated examples plus 1 previously unrun lifecycle-review example; applied effort was within range on 8/8 |
| Request latency | 103 ms minimum, 134.5 ms median, 298 ms maximum |
| Usage | 25,732 input tokens; 2,268 output tokens; about $0.001081 estimated by the client's $0.042/million-input-token rate |

Latency is the client's Jev request measurement. It excludes fixture setup, Pi
startup, coding-model inference, tools, and any human repair work. The cost is a
client estimate, not an invoice.

### Failures that changed the policy

The effort judgment was useful even when task-relationship confidence was low.
The original policy discarded both judgments whenever relationship confidence
fell below 0.8, leaving substantial engineering work at insufficient effort.

| Synthetic request | Baseline Jev judgments | Old applied level | Follow-up applied level |
| --- | --- | --- | --- |
| Extension lifecycle review | high, confidence 0.63; new task, confidence 0.43 | medium | high |
| Payment retry work expands to crash/idempotency analysis | high, confidence 0.65; continuation, confidence 0.34 | low | high |
| Race diagnosis requiring an unseen screenshot | high, confidence 0.97; new task, confidence 0.60 | low | high |

The revised policy lets independently justified increases proceed despite an
uncertain task boundary. Uncertain boundaries still prevent reductions and
fresh-task baseline resets. Escalations above high still require their own
confidence gate. This fixes the policy coupling without lowering the 0.8 floor.

The relationship question now distinguishes unavailable working materials from
an unidentified objective, and recognizes changed scope within the same
deliverable as a continuation. Relationship confidence remained below 0.8 on
several follow-up examples, so the successful policy outcomes should not be
attributed to the wording change alone.

### Controls and remaining conservative behavior

An unrelated literal formatting task after max effort selected and applied
minimal. A fresh bounded review after max applied high. A continuation of an
xhigh investigation inherited xhigh, while an unresolved reference to an earlier
option inherited the current high level. These controls held in the follow-up.

A trivial example containing quoted routing-injection text selected minimal
without following the instruction to choose max. Its confidence was only 0.58,
so the policy retained high. The probability distribution was split mainly among
minimal (0.64), off (0.16), and low (0.13). This is a remaining conservative
latency trade-off; the pilot does not calibrate a replacement threshold or prove
that top-choice confidence is the best gate for adjacent effort levels.

## Expansion: 17 fresh scenarios

The operator requested at least 20-30 tests. The expansion added 17 previously
unrun scenarios, bringing distinct live coverage to 30. Its separate authorized
ceiling was 17 submissions; the other request-size, deadline, spend, and no-retry
limits were unchanged. Prompts and production policy were frozen during all 17
calls at the revised source hash listed below. The fixture host also supplied
registered skill and prompt descriptions for invocation cases.

Coverage included mechanical bulk edits, sorting, translation, HTTP explanation,
security review, incident diagnosis, scheduler design, quoted instruction attacks,
continuations, migration scope changes, skill/template invocations, Spanish input,
and a restricted supported-level set.

| Measure | Expansion result |
| --- | --- |
| Selected effort within predeclared range | 16/17 |
| Selected task relationship within predeclared range | 17/17 |
| Applied effort within predeclared range | 12/17 |
| Live request failures | 0 |
| Combined usage across all 37 calls | 48,242 input tokens, 4,210 output tokens; about $0.002026 estimated |

Combined request latency was 103-298 ms, with a median of 152 ms. These are still
Jev request timings, not coding-task completion times.

All five applied-level mismatches are retained:

| Request | Jev effort / confidence | Live applied level | Assessment |
| --- | --- | --- | --- |
| Mechanical replacement across 50 Markdown files | low / 0.88 | high | Relationship confidence 0.79 blocked reduction |
| Sort three ISO dates | minimal / 0.76 | high | Effort confidence blocked reduction |
| Independent HTTP 404/410 explanation | minimal / 0.56 | high | Conservative fallback; minimal was also outside the predeclared low/medium label range |
| JSON-formatting prompt invocation | minimal / 0.62 | high | Relationship confidence 0.77 blocked reduction |
| Incident investigation with competing causes | xhigh / 0.75 | medium | Under-routing bug: weak xhigh evidence fell back below high |

The incident result allocated probability 0.78 to xhigh and 0.22 to high, with
zero on lower levels. Its task relationship was new_task with confidence 0.77.
Preserving medium was therefore a policy-composition error. After the frozen
live round, the fallback was changed to the already-computed high-or-current
baseline. Offline replay now applies high to this captured result. This one-line
fix was not followed by another live call; all 17 authorized submissions had
already been used.

At the end of that round, the four conservative expansion mismatches remained.
No thresholds or expected live ranges were loosened to improve the reported live
score. The later band-policy replay is reported separately below. The HTTP example also
shows the subjectivity of hand-assigned effort ranges; no downstream answer was
generated to establish whether minimal would be sufficient.

Expanded raw evidence and the executable harness are retained at:

`/tmp/effort-live-expanded.WBpcKs/`

## Band-policy replay

A later policy change addresses ambiguity between off, minimal, and low without
weakening task-boundary protection. For a weak exact choice within that band,
combined probability of at least 0.9 permits the highest supported band member,
normally low. Exact high-confidence choices retain their original behavior.
The task-relation gate stays at confidence 0.8. Escalation and exact-downgrade
confidence gates are now named independently; their values remain 0.8.

This was an offline replay of the existing 37 answers. Prompts did not change
and no additional live calls were made. Three captured cases now use low instead
of high: sorting dates, explaining HTTP 404/410, and the trivial request containing
quoted routing-injection text. The bulk replacement and JSON-formatting cases
still retain high because the task-boundary gate blocks their reductions.

| Evaluation | Acceptable range | Preferred range |
| --- | --- | --- |
| Frozen live results, across all rounds | 33/37 | 28/37 |
| Current policy replay of the same answers | 37/37 | 35/37 |
| Current replay, latest answer per distinct scenario | 30/30 | 28/30 |

Preferred ranges are the predeclared pilot targets. Acceptable ranges are
retrospective human policy annotations: minimum reasoning allocation for explicit
tasks, or preservation for unresolved references and continuations. They do not
prove that higher effort is equally good or that the coding result is correct.
The HTTP explanation admits minimal as acceptable while retaining low/medium as
preferred. This avoids treating a subjective preference as an observed failure.

## Offline regression checks

`npm test` runs 63 checks without network access:

- Replay all 37 captured answers and report acceptable and preferred ranges separately.
- Check band cutoffs, floating-point boundaries, supported levels, and exclusion of inherit/medium probability.
- Preserve task-boundary and image protections, including max-effort tasks.
- Keep advisory mode non-mutating and reject late answers after manual override.
- Route queued delivery without downgrading and exclude extension-injected messages.
- Skip ambiguous dequeue/requeue expansion matches instead of guessing or sending expanded skill bodies.
- Restore mode/history from the active branch while retaining session-wide attempt accounting.
- Apply attempt 50, pause immediately, confirm replenishment, and reconstruct reset epochs.
- Distinguish agent-run duration from judge latency.

The captured cases are in `tests/fixtures/jev-routing.json`. `observedApplied`
preserves the frozen live result, `expectedApplied` specifies current implementation
behavior, and `acceptableEfforts` and `preferredEfforts` contain separate policy
expectations. Passing regressions does not imply that all preferred ranges match;
the test output names remaining misses. Historical live outcomes are unchanged.
Pi APIs are mocked, so these checks do not establish real-host event ordering.

## Evidence and limitations

Raw requests, responses, predeclared ranges, source snapshots, and the executable
pilot harness were retained outside the repository at:

`/tmp/effort-live-pilot.mGoKYS/`

Source SHA-256 hashes:

- Baseline: `d6b09634df884b4be90dbc4be0b177625e41810c70a873f2bafe5cada74ecbbc`
- Revised: `9c28740d8c93b8af00d0e1aaab2c4a712614b33e7dc55ff914b6b82053ab96a7`

Initial harness setup encountered an ESM resolution issue and then 12 local
validation failures from cross-VM object prototypes. These made zero HTTP
submissions. The harness now serializes requests into plain JSON before calling
the client; those setup failures are retained separately and excluded from live
results.

This is a small, hand-labelled diagnostic pilot. Seven initial follow-up cases
repeat examples used to identify the first issue; one initial follow-up and all
17 expansion cases were previously unrun. There are no
repeatability estimates, calibrated confidence thresholds, or downstream coding
quality measurements. The findings justify separating the two policy gates;
they do not establish an optimal effort level for real engineering tasks.

## Session-effort replay: September 23 production messages

Production logs from one Windows machine showed the task-relationship policy
rarely reached its 0.8 relationship gate: its task anchor was empty in 10 of 11
sessions, so 38 reductions were blocked and 81 of 90 decisions stayed at the
`xhigh` session default. Jev never selected xhigh or max in 85 calls, including
authorization and checkpoint-redesign work. Copilot session usage also showed that
mid-session effort changes restarted the prompt cache.

The revised source replaced the relationship question with session effort, a
stakes Noul, and recent-conversation excerpts. A replay harness ran the actual
source in a mocked Pi host against the 86 routed messages of 11 sessions, using
the real transcripts for context and the recorded delivery mode. It made 83 live
Jev requests with 0 failures; 3 acknowledgements skipped Jev. As in the first
pilot, an initial run hit 83 local cross-VM validation failures before any HTTP
submission; the harness now serializes requests into plain JSON.

Reference labels were assigned by the routed coding model reading each message
in session context; they are one judgment, not outcomes.

| Policy | Match | Above label | Below label | Mid-session changes |
| --- | --- | --- | --- | --- |
| Production relationship policy | 14 | 72 | 0 | 1 |
| Revised, stakes 0.5, gated baseline return | 30 | 55 | 1 | 5 |
| Revised, stakes 0.75, baseline return ungated | 52 | 33 | 1 | 3 |
| Revised, stakes 0.8, baseline return ungated | 55 | 30 | 1 | 2 |
| Revised, stakes 0.85, baseline return ungated | 58 | 25 | 3 | 3 |

Stakes probabilities for the six xhigh-labelled design and redesign messages
were 0.80 to 0.86; the lowest was exactly 0.80. The source uses 0.75 for margin.
The remaining below-label case was an analysis request with stakes 0.23. A
streak of one matched 2 more messages at 0.75 with the same number of changes;
two was kept to protect the cache on other workloads. The downgrade confidence
setting did not change results between 0.7 and 0.8.

The sweep reused the live answers even where a policy variant would have sent a
different `current_effort`. This is one machine, one day, and one labeller, with
no repeatability or downstream quality measurement. The harness and answer cache
were retained outside the repository as `router-replay-live.mjs` and
`router-replay-cache.json` in the Windows temporary directory.

Source SHA-256: `b5a71522e5e8393c0c77a2ff7baa3b7d359caad562a5fc7ab790f6c3dbdd4645`
