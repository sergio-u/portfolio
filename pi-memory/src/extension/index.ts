// PI Memory Extension -- entry point.
//
// Phase 3 partial: SKILL.md bodies for memory-note and
// memory-checkpoint are fleshed out; resources_discover gates
// memory-note on [note].smart_routing; the lifecycle hooks
// (session_before_compact and session_shutdown) do checkpoint
// bookkeeping. /checkpoint is a manual fallback that also does
// deterministic bookkeeping. LLM-driven observation extraction inside
// memory-checkpoint is deferred until a clean PI-side skill-invocation
// bridge exists; the auto-invocable memory-note skill works today via
// system-prompt surfacing. AnythingLLM-backed semantic recall (Phase 3)
// is deferred pending AnythingLLM-side debugging.

import * as path from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { registerTools } from "./tools/index.ts";
import { registerSessionStart } from "./hooks/session_start.ts";
import { registerBeforeAgentStart } from "./hooks/before_agent_start.ts";
import { registerSessionBeforeCompact } from "./hooks/session_before_compact.ts";
import { registerSessionShutdown } from "./hooks/session_shutdown.ts";
import { registerNote } from "./commands/note.ts";
import { registerRecall } from "./commands/recall.ts";
import { registerSetContext } from "./commands/set_context.ts";
import { registerMemoryDoctor } from "./commands/memory_doctor.ts";
import { registerCheckpoint } from "./commands/checkpoint.ts";
import { registerMemoryBootstrap } from "./commands/memory_bootstrap.ts";
import { registerDumpCommands } from "./commands/dump.ts";
import { tryLoadEffectiveConfig } from "./config/loader.ts";

// Resolve the package root from this file's URL so resources_discover
// can emit absolute paths regardless of the user's cwd. This file lives
// at <pkg>/src/extension/index.ts, so the package root is two levels up.
const EXTENSION_DIR = path.dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = path.resolve(EXTENSION_DIR, "..", "..");
const SKILLS_ROOT = path.join(PACKAGE_ROOT, "skills");

export default function registerMemoryExtension(pi: ExtensionAPI): void {
  registerTools(pi);
  registerSessionStart(pi);
  registerBeforeAgentStart(pi);
  registerSessionBeforeCompact(pi);
  registerSessionShutdown(pi);
  registerNote(pi);
  registerRecall(pi);
  registerSetContext(pi);
  registerMemoryDoctor(pi);
  registerCheckpoint(pi);
  registerMemoryBootstrap(pi);
  registerDumpCommands(pi);

  // Phase 4 command still stubbed.
  pi.registerCommand("dream", {
    description: "Run the Dream consolidation pass (every 15 days; manual invocation).",
    handler: async (_args, ctx) => {
      ctx.ui.notify("/dream -- not yet implemented (Phase 4)");
    },
  });

  pi.on("resources_discover", (_event, ctx) => {
    // Single source of truth for skill loading. We do NOT declare
    // pi.skills in package.json -- if we did, all skills would be
    // bulk-loaded eagerly and the smart_routing gate below would be
    // bypassed (memory-note's description would always appear in the
    // system prompt). See PI review note in the v0.3 commit message.
    //
    // memory-checkpoint, memory-recall, and memory-dream always load;
    // memory-checkpoint and memory-dream are disable-model-invocation
    // and only fire when invoked explicitly. The auto-invocable
    // memory-note skill is gated on [note].smart_routing so a user can
    // opt out of LLM-driven capture entirely (privacy, system-prompt
    // budget). When smart_routing is false, /note still works
    // deterministically; the skill description just isn't surfaced to the LLM.
    //
    // Paths are absolute (derived from import.meta.url at module load)
    // so PI's skill loader resolves them regardless of the user's cwd.
    const loaded = tryLoadEffectiveConfig(ctx.cwd);
    const smartRouting = loaded.ok ? loaded.config.note.smart_routing : true;
    const skillPaths = [
      path.join(SKILLS_ROOT, "memory-checkpoint"),
      path.join(SKILLS_ROOT, "memory-recall"),
      path.join(SKILLS_ROOT, "memory-dream"),
    ];
    if (smartRouting) {
      skillPaths.push(path.join(SKILLS_ROOT, "memory-note"));
    }
    return { skillPaths };
  });
}
