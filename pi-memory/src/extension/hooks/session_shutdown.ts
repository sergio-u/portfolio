// session_shutdown hook -- bookkeeping at session end.
//
// Current runtime behavior is intentionally quiet: update the internal
// checkpoint marker only, and do not write a markdown shutdown line.
// Durable notes should come from /note, /checkpoint, memory-note, or the
// future LLM-driven memory-checkpoint workflow.
//
// Gated on [capture].on_session_shutdown.

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { tryLoadEffectiveConfig } from "../config/loader.ts";
import {
	STATE_KEYS,
	type CheckpointMarker,
} from "../util/session-state.ts";

export function registerSessionShutdown(pi: ExtensionAPI): void {
	pi.on("session_shutdown", async (_event, ctx) => {
		const loaded = tryLoadEffectiveConfig(ctx.cwd);
		if (!loaded.ok || !loaded.config.capture.on_session_shutdown) return;

		const marker: CheckpointMarker = {
			entry_id: ctx.sessionManager.getLeafId() ?? "",
			ts: new Date().toISOString(),
			mode: "shutdown",
		};
		pi.appendEntry(STATE_KEYS.CHECKPOINT_MARKER, marker);
	});
}
