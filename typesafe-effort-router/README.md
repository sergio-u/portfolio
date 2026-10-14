# TypeSafe effort router

A Pi extension that asks a small judge model (Jev, from
[TypeSafe](https://www.npmjs.com/package/pi-typesafe)) how much reasoning effort
each request needs, then sets Pi's thinking level. Model selection stays manual.
The goal is correct, complete work; total task time is secondary, and monetary
cost is not a routing objective.

It lived in my Pi configuration as `extensions/typesafe-effort-router` from
September 22 to October 5, 2026. [PILOT.md](PILOT.md) records the live
evaluation.

## Results

A replay ran the extension against 86 real messages from 11 of my Pi sessions,
with the original transcripts as context (83 live Jev calls, no failures). A
reference label for each message came from the coding model reading it in
context.

| Policy | Matched label | Above label | Below label | Mid-session changes |
| --- | --- | --- | --- | --- |
| Previous production policy | 14 | 72 | 0 | 1 |
| Current policy (stakes threshold 0.75) | 52 | 33 | 1 | 3 |

The previous policy depended on a task-relationship judgment that rarely reached
its confidence gate, so 81 of 90 production decisions stayed at the `xhigh`
session default. The earlier synthetic pilot (37 live calls; the first 20 had a
median Jev latency of 134.5 ms and cost about $0.001 together) found that
discarding a confident effort judgment whenever the task boundary was uncertain
left substantial engineering requests at low or medium effort. Both findings
shaped the current policy.

The evidence is one machine, one day, and one labeller, with no repeatability or
downstream quality measurement. See [PILOT.md](PILOT.md) for all rounds.

## How it routes

One request asks Jev two independent questions: which effort level fits (any
level the model supports, or `inherit`), and how likely a subtle mistake would be
costly or hard to detect. The second covers authorization and security,
data integrity, public API design, production systems, and irreversible
operations.

High is the baseline for substantive engineering. Lower levels fit mechanical or
tightly scoped work; xhigh fits interacting systems, hard diagnosis, and
consequential design; max needs a plausible benefit from longer exploration.
Importance, requested thoroughness, file count, or tool activity alone do not
justify escalation.

The router keeps one effort per session and changes it reluctantly, because a
change restarts the provider prompt cache. On Copilot-served models, 12 of 14
observed mid-session changes rewrote the full cached context.

- The first judgment in a session is compared with high. `inherit` or an
  uncertain answer applies high.
- Raises apply immediately. Xhigh and max need a confident judgment; otherwise
  effort rises only to high.
- Reductions need a confident judgment plus either two consecutive reduction
  judgments or 10 idle minutes, when the cache is already cold.
- A stakes probability of at least 0.75 raises a high judgment to xhigh.

| Decision | Gate |
| --- | --- |
| Escalate above high | Effort confidence at least 0.8 |
| Apply a lower effort | Two consecutive judgments or a cold cache; below high, also confidence at least 0.8 |
| Resolve uncertainty within off/minimal/low | Combined probability at least 0.9 (applies the highest supported member, normally low) |
| Raise high to xhigh for stakes | Stakes probability at least 0.75 |

These are uncalibrated policy settings. Confidence is not the probability that a
task succeeds.

Each request includes up to four earlier user and assistant messages, 600
characters each, so Jev can resolve references such as "the approved plan".
Tool results, thinking, and images are excluded. Because Jev cannot see images,
an image never justifies a reduction, and image-only inputs or service failures
keep at least high.

Queued messages (Pi 0.87 or newer) route when Pi delivers them. Steering joins
the running task, so it can raise effort but never lower it. A queued skill or
prompt template whose text no longer matches the recorded input is skipped rather
than guessed. Any new input, mode change, model change, tree navigation, or
shutdown invalidates pending decisions; requests have a five-second limit and no
retries.

## Controls

| Command | Effect |
| --- | --- |
| `/effort-router advisory` | Show the suggested effort without changing it; saves advisory as the default |
| `/effort-router auto` | Apply decisions for idle user input; saves auto as the default |
| `/effort-router status` | Show mode, remaining budget, consent, and policy settings |
| `/effort-router history` | Show the last five decisions, skips, overrides, or run durations |
| `/effort-router manual`, `/effort-router revoke` | Stop routing and save manual; revoke also withdraws consent |

`Alt+R` toggles between auto and manual through the same consent checks. The
footer shows `router: auto`, `router: manual`, or a suggestion such as
`router: advisory -> high`. Changing effort by hand pauses routing for the
current session, including after reload, without changing the default.

## Consent, budget, and history

Routing starts disabled until the user consents and saves an enabled default.
Consent covers the current input, recent message excerpts, any skill or template
description, an image-presence flag, the model id, and effort settings. The
router does not read files, tool results, thinking, or image bytes. Consent is
stored in `~/.pi/agent/typesafe-effort-router.json`.

Only the interactive parent session starts routing from saved preferences.
Headless and child runs need the explicit `--effort-router` flag and existing
consent, so loading the extension never silently changes a child's effort.
Revoking stops the current instance at once, and other instances check consent
before sending or applying a request.

Each budget epoch allows 50 evaluations, counting failures. After the 50th the
router switches to manual; starting another epoch needs confirmation in the
interactive UI. Decisions are stored as Pi custom session entries, outside model
context, with no prompt text or image data. They record the recommendation,
applied level, confidences, stakes probability, token usage, judge latency, and
how long each agent run took.

## Install

The extension imports TypeSafe's library through a fixed relative path, so it
must live in Pi's agent directory next to a Pi-scoped install of `pi-typesafe`
(version 0.7.1 at the time):

```bash
pi install npm:pi-typesafe
cp -R typesafe-effort-router ~/.pi/agent/extensions/
```

Pi 0.87 or newer and Node.js 22.19 or newer are required. Sign in with `/typesafe login`
or set `TYPESAFE_API_KEY`. After reloading Pi, `/effort-router advisory` asks for
consent and starts recommending levels.

## Tests

Run these from the installed folder; typechecking and tests use the Pi-scoped
`pi-typesafe` install, the same library production uses.

```sh
npm ci --ignore-scripts --include=dev
npm run typecheck
npm test
```

The tests replay captured Jev answers through the real extension in a mocked Pi
host, without credentials or network access. They cover lifecycle safeguards,
queued delivery, downgrade blocking, extension-message exclusion, skill privacy,
and branch restoration. Each case stores its frozen live result, the expected
result, an acceptable effort range, and a preferred range. Acceptable ranges
catch under-routing; preferred ranges expose over-routing. Neither measures
downstream coding quality.
