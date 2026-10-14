import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import * as fs from "node:fs";
import * as path from "node:path";
import { tmpdir } from "node:os";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";
import * as ai from "@earendil-works/pi-ai";
import * as typesafe from "../../../npm/node_modules/pi-typesafe/dist/index.js";

const source = readFileSync(new URL("../index.ts", import.meta.url), "utf8");
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2023 },
}).outputText;
const fixtures = JSON.parse(readFileSync(new URL("./fixtures/jev-routing.json", import.meta.url), "utf8")).cases;
const allLevels = ["off", "minimal", "low", "medium", "high", "xhigh", "max"];

function choiceAnswer(question, selected) {
  const keys = Object.keys(question.criteria);
  return {
    type: "choice", choice: selected, confidence: 0.99,
    probabilities: Object.fromEntries(keys.map(key => [key, key === selected ? 0.99 : 0.01 / (keys.length - 1)])),
  };
}

// Execute the actual extension, with Pi and inference mocked. No API key or network is used.
async function harness(t, example, evaluate, entries = []) {
  const directory = mkdtempSync(path.join(tmpdir(), "effort-router-test-"));
  writeFileSync(path.join(directory, "typesafe-effort-router.json"), JSON.stringify({
    version: 2, consented: true, defaultMode: "auto",
  }));
  let level = example.previous;
  let seeding = Boolean(example.activeTask);
  let idle = true;
  let clock = 0;
  let footerStatus;
  const calls = [];
  const notices = [];
  const handlers = new Map();
  const commands = new Map();
  const shortcuts = new Map();
  const levels = example.levels ?? allLevels;
  const model = {
    provider: "openai", id: "gpt-6-astra", reasoning: true,
    thinkingLevelMap: Object.fromEntries(allLevels.map(value => [value, levels.includes(value) ? value : null])),
  };
  const judge = { evaluate: async (request, options) => {
    if (seeding) return {
      answers: { effort: choiceAnswer(request.questions.effort, example.previous), task_relation: choiceAnswer(request.questions.task_relation, "new_task") },
      model: "offline-seed", usage: { input_tokens: 0, output_tokens: 0 }, elapsedMs: 0,
    };
    calls.push(request);
    return evaluate ? evaluate(request, options) : example.result;
  } };
  const ctx = {
    mode: "tui", hasUI: true, model, isIdle: () => idle,
    sessionManager: {
      getEntries: () => entries,
      getBranch: () => example.branchEntries ?? entries,
    },
    ui: {
      setStatus: (_key, text) => { footerStatus = text; },
      notify: message => notices.push(message),
      confirm: async () => example.confirm ?? true,
    },
  };
  const setLevel = next => {
    const previousLevel = level;
    level = ai.clampThinkingLevel(model, next);
    if (level !== previousLevel) handlers.get("thinking_level_select")?.({ level, previousLevel }, ctx);
  };
  const pi = {
    on: (name, handler) => handlers.set(name, handler),
    registerFlag() {}, getFlag: () => false, getCommands: () => example.commands ?? [],
    registerCommand: (name, command) => commands.set(name, command),
    registerShortcut: (key, shortcut) => shortcuts.set(key, shortcut),
    getThinkingLevel: () => level, setThinkingLevel: setLevel,
    appendEntry: (customType, data) => entries.push({ type: "custom", customType, data }),
  };
  const exports = {};
  const dependencies = {
    "node:fs": fs, "node:path": path, "@earendil-works/pi-ai": ai,
    "@earendil-works/pi-coding-agent": { getAgentDir: () => directory },
    "../../npm/node_modules/pi-typesafe/dist/index.js": {
      ...typesafe, createTypeSafe: () => judge,
      authState: () => ({}), describeAuth: () => ({ level: "ok", text: "offline fixture" }),
    },
  };
  vm.runInNewContext(code, {
    exports,
    require: name => {
      assert.ok(name in dependencies, `Unexpected dependency: ${name}`);
      return dependencies[name];
    },
    process: { pid: process.pid, env: {} }, AbortController, AbortSignal,
    performance: { now: () => clock },
  }, { filename: "router-under-test.js" });
  exports.default(pi);
  t.after(async () => {
    await handlers.get("session_shutdown")({}, ctx);
    rmSync(directory, { recursive: true, force: true });
  });
  await handlers.get("session_start")({}, ctx);
  const input = (text, extra = {}) => handlers.get("input")({ text, source: "interactive", ...extra }, ctx);
  if (seeding) {
    await input(example.activeTask);
    seeding = false;
  }
  return {
    input, setLevel, entries, calls, notices,
    get level() { return level; },
    get status() { return footerStatus; },
    get decision() { return entries.filter(entry => entry.data.kind === "decision").at(-1)?.data; },
    command: args => commands.get("effort-router").handler(args, ctx),
    shortcut: key => shortcuts.get(key).handler(ctx),
    deliverQueued: (text, images) => handlers.get("message_start")({
      message: {
        role: "user",
        content: [
          { type: "text", text },
          ...(images?.length ? images : []),
        ],
        timestamp: Date.now(),
      },
    }, ctx),
    emit: name => handlers.get(name)?.({}, ctx),
    setIdle: value => { idle = value; },
    setClock: value => { clock = value; },
  };
}

const evaluations = [];
for (const example of fixtures) {
  test(`captured judgment: ${example.id}`, async t => {
    const router = await harness(t, example);
    await router.input(example.message, { images: example.imageAttached ? [{}] : undefined });
    assert.equal(router.calls.length, 1);
    assert.equal(router.level, example.expectedApplied);
    assert.equal(router.status, "router: auto");
    assert.ok(example.acceptableEfforts.includes(router.level), `Outside acceptable range: ${example.id} -> ${router.level}`);
    evaluations.push({ id: example.id, applied: router.level, preferred: example.preferredEfforts.includes(router.level) });
    assert.equal(router.decision.judgeLatencyMs, example.result.elapsedMs);
    assert.equal(router.decision.elapsedMs, undefined);
    assert.equal(router.calls[0].state.active_task, example.activeTask ?? null);
  });
}

test("evaluation reports acceptable and preferred effort separately", t => {
  assert.equal(evaluations.length, fixtures.length);
  const liveAcceptable = fixtures.filter(example => example.acceptableEfforts.includes(example.observedApplied)).length;
  const livePreferred = fixtures.filter(example => example.preferredEfforts.includes(example.observedApplied)).length;
  const preferred = evaluations.filter(result => result.preferred).length;
  const distinct = [...new Map(evaluations.map(result => [result.id.split("/")[1], result])).values()];
  t.diagnostic(`Frozen live: acceptable ${liveAcceptable}/${fixtures.length}, preferred ${livePreferred}/${fixtures.length}.`);
  t.diagnostic(`Current replay: acceptable ${evaluations.length}/${fixtures.length}, preferred ${preferred}/${fixtures.length}; latest per scenario preferred ${distinct.filter(result => result.preferred).length}/${distinct.length}.`);
  for (const result of evaluations.filter(result => !result.preferred)) {
    t.diagnostic(`Preference miss retained: ${result.id} -> ${result.applied}`);
  }
});

const simple = fixtures.find(example => example.id === "revised-live/fresh-review-after-max");

const bandCases = [
  { name: "combined probability at cutoff selects low", probabilities: { minimal: 0.6, low: 0.3, high: 0.1 }, expected: "low", reason: "low-band-downgrade" },
  { name: "below cutoff retains high", probabilities: { minimal: 0.6, low: 0.29, high: 0.11 }, expected: "high", reason: "uncertain-downgrade-blocked" },
  { name: "inherit does not contribute to low-band probability", probabilities: { minimal: 0.6, low: 0.25, inherit: 0.15 }, expected: "high", reason: "uncertain-downgrade-blocked" },
  { name: "medium does not contribute to low-band probability", probabilities: { minimal: 0.6, low: 0.25, medium: 0.15 }, expected: "high", reason: "uncertain-downgrade-blocked" },
  { name: "task-boundary protection remains unchanged", previous: "max", relationConfidence: 0.79, probabilities: { minimal: 0.67, low: 0.32, high: 0.01 }, expected: "max", reason: "task-boundary-downgrade-blocked" },
  { name: "image protection remains unchanged", imageAttached: true, probabilities: { minimal: 0.67, low: 0.32, high: 0.01 }, expected: "high", reason: "image-downgrade-blocked" },
  { name: "only supported band members can be selected", levels: ["off", "minimal", "high"], probabilities: { off: 0.25, minimal: 0.7, high: 0.05 }, expected: "minimal", reason: "low-band-downgrade" },
  { name: "models without a low band retain the normal fallback", levels: ["medium", "high"], choice: "medium", probabilities: { medium: 0.6, high: 0.4 }, expected: "high", reason: "uncertain-downgrade-blocked" },
  { name: "confident exact choices are unchanged", confidence: 0.95, probabilities: { minimal: 0.97, low: 0.02, high: 0.01 }, expected: "minimal", reason: "recommended" },
  { name: "advisory displays the low-band target without applying it", advisory: true, probabilities: { minimal: 0.6, low: 0.3, high: 0.1 }, expected: "high", target: "low", reason: "low-band-downgrade" },
];
for (const example of bandCases) {
  test(`band policy: ${example.name}`, async t => {
    const router = await harness(t, { ...example, previous: example.previous ?? "high" }, request => ({
      answers: {
        effort: {
          type: "choice", choice: example.choice ?? "minimal", confidence: example.confidence ?? 0.5,
          probabilities: Object.fromEntries(Object.keys(request.questions.effort.criteria).map(level => [level, example.probabilities[level] ?? 0])),
        },
        task_relation: { ...choiceAnswer(request.questions.task_relation, "new_task"), confidence: example.relationConfidence ?? 0.99 },
      },
      model: "offline-policy-fixture", usage: { input_tokens: 0, output_tokens: 0 }, elapsedMs: 0,
    }));
    if (example.advisory) await router.command("advisory");
    await router.input("Format the supplied literal data without changing it.", { images: example.imageAttached ? [{}] : undefined });
    assert.equal(router.level, example.expected);
    assert.equal(router.decision.target, example.target ?? example.expected);
    assert.equal(router.decision.reason, example.reason);
  });
}

test("uncertain task identity still blocks reducing an established max level", async t => {
  const example = fixtures.find(item => item.id === "baseline-live/extension-review");
  const router = await harness(t, { ...example, previous: "max" });
  await router.input(example.message);
  assert.equal(router.level, "max");
  assert.equal(router.decision.reason, "task-boundary-downgrade-blocked");
});

test("advisory records the fresh-task target without changing effort", async t => {
  const router = await harness(t, simple);
  await router.command("advisory");
  await router.input(simple.message);
  assert.equal(router.level, "max");
  assert.equal(router.decision.target, "high");
  assert.equal(router.decision.applied, "max");
  assert.equal(router.status, "router: advisory -> high");
});

test("alt+r toggles auto and manual through the shared persisted mode path", async t => {
  const router = await harness(t, simple);
  assert.equal(router.status, "router: auto");
  await router.shortcut("alt+r");
  assert.equal(router.status, "router: manual");
  await router.shortcut("alt+r");
  assert.equal(router.status, "router: auto");
  assert.equal(router.entries.some(entry => entry.data.kind === "budget_reset"), false);
});

test("alt+r leaves advisory mode by switching to manual", async t => {
  const router = await harness(t, simple);
  await router.command("advisory");
  assert.equal(router.status, "router: advisory");
  await router.shortcut("alt+r");
  assert.equal(router.status, "router: manual");
});

test("manual override discards a late successful judgment even if inference ignores abort", async t => {
  const began = Promise.withResolvers();
  const pending = Promise.withResolvers();
  const router = await harness(t, { previous: "low" }, async () => { began.resolve(); return pending.promise; });
  const input = router.input("Review the retry helper for correctness.");
  await began.promise;
  await router.command("manual");
  router.setLevel("medium");
  pending.resolve(simple.result);
  await input;
  assert.equal(router.level, "medium");
  assert.equal(router.decision.reason, "stale-or-cancelled");
  assert.equal(router.status, "router: manual");
});

test("queued inputs route when delivered and cannot downgrade current effort", async t => {
  const example = fixtures.find(item => item.id === "revised-live/fresh-trivial-after-max");
  const router = await harness(t, { ...example, previous: "xhigh", activeTask: undefined });
  router.setIdle(false);
  await router.input(example.message, { streamingBehavior: "followUp" });
  assert.equal(router.calls.length, 0);
  await router.deliverQueued(example.message);
  assert.equal(router.calls.length, 1);
  assert.equal(router.level, "xhigh");
  assert.equal(router.decision.reason, "queued-downgrade-blocked");
  assert.equal(router.decision.delivery, "followUp");
});

test("ambiguous expanded queued skills are skipped instead of matched by guess", async t => {
  const example = fixtures.find(item => item.id === "expanded-live/skill-review-invocation");
  const router = await harness(t, example);
  router.setIdle(false);
  await router.input("/skill:old", { streamingBehavior: "steer" });
  // Simulate dequeue-to-editor removing old, then queue a different expanding skill.
  await router.input(example.message, { streamingBehavior: "steer" });
  await router.deliverQueued("SECRET EXPANDED SKILL BODY");
  assert.equal(router.calls.length, 0);
});

test("a stale steering expansion marker cannot intercept an extension follow-up", async t => {
  const router = await harness(t, simple);
  router.setIdle(false);
  await router.input("/skill:removed", { streamingBehavior: "steer" });
  await router.input(simple.message, { source: "extension", streamingBehavior: "followUp" });
  await router.deliverQueued(simple.message);
  assert.equal(router.calls.length, 0);
});

test("extension-injected queued user messages are not routed", async t => {
  const router = await harness(t, simple);
  router.setIdle(false);
  await router.input(simple.message, { source: "extension", streamingBehavior: "steer" });
  await router.deliverQueued(simple.message);
  assert.equal(router.calls.length, 0);
});

test("session restore reads mode from the active branch but counts attempts across branches", async t => {
  const manual = { type: "custom", customType: "typesafe-effort-router", data: { version: 1, kind: "mode", mode: "manual" } };
  const abandonedAuto = { type: "custom", customType: "typesafe-effort-router", data: { version: 1, kind: "mode", mode: "auto" } };
  const abandonedAttempt = { type: "custom", customType: "typesafe-effort-router", data: { version: 1, kind: "attempt" } };
  const router = await harness(t, { previous: "high", branchEntries: [manual] }, undefined,
    [manual, abandonedAuto, abandonedAttempt]);
  assert.equal(router.status, "router: manual");
  await router.command("status");
  assert.match(router.notices.at(-1), /attempts: 1\/50/);
  assert.equal(router.calls.length, 0);
});

test("attempt 50 applies its decision and immediately pauses routing", async t => {
  const entries = Array.from({ length: 49 }, () => ({
    type: "custom", customType: "typesafe-effort-router", data: { version: 1, kind: "attempt" },
  }));
  const router = await harness(t, { ...simple, previous: "high", activeTask: undefined }, undefined, entries);
  await router.input(simple.message);
  assert.equal(router.calls.length, 1);
  assert.equal(router.status, "router: manual");
  assert.match(router.notices.at(-1), /manual after 50 attempts/);
});

test("confirmed re-enable starts a recorded fresh 50-attempt epoch", async t => {
  const entries = Array.from({ length: 50 }, () => ({
    type: "custom", customType: "typesafe-effort-router", data: { version: 1, kind: "attempt" },
  }));
  const router = await harness(t, { previous: "high" }, undefined, entries);
  assert.equal(router.status, "router: manual");
  await router.command("auto");
  assert.equal(router.status, "router: auto");
  assert.equal(router.entries.filter(entry => entry.data.kind === "budget_reset").length, 1);
  await router.command("status");
  assert.match(router.notices.at(-1), /attempts: 0\/50/);
});

test("declining replenishment keeps the exhausted session manual", async t => {
  const entries = Array.from({ length: 50 }, () => ({
    type: "custom", customType: "typesafe-effort-router", data: { version: 1, kind: "attempt" },
  }));
  const router = await harness(t, { previous: "high", confirm: false }, undefined, entries);
  await router.shortcut("alt+r");
  assert.equal(router.status, "router: manual");
  assert.equal(router.entries.some(entry => entry.data.kind === "budget_reset"), false);
});

test("reload reconstructs attempts after the latest session-wide budget reset", async t => {
  const attempt = () => ({ type: "custom", customType: "typesafe-effort-router", data: { version: 1, kind: "attempt" } });
  const reset = { type: "custom", customType: "typesafe-effort-router", data: { version: 1, kind: "budget_reset", previousAttempts: 50 } };
  const entries = [...Array.from({ length: 50 }, attempt), reset, ...Array.from({ length: 3 }, attempt)];
  const router = await harness(t, { previous: "high" }, undefined, entries);
  await router.command("status");
  assert.match(router.notices.at(-1), /attempts: 3\/50/);
});

test("agent timing spans retries and reports duration separately from judge latency", async t => {
  const router = await harness(t, { previous: "high" });
  router.setClock(100);
  router.setIdle(false);
  await router.emit("agent_start");
  router.setClock(900);
  await router.emit("agent_start");
  await router.emit("agent_settled");
  assert.equal(router.entries.filter(entry => entry.data.kind === "run").length, 0);
  router.setClock(1600);
  router.setIdle(true);
  await router.emit("agent_settled");
  const run = router.entries.find(entry => entry.data.kind === "run").data;
  assert.equal(run.agentRunDurationMs, 1500);
  assert.equal(run.judgeLatencyMs, undefined);
  assert.equal(run.success, undefined);
});
