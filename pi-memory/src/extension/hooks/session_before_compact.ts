// session_before_compact hook — bookkeeping for the upcoming compaction
// pass. The hook updates the memory-checkpoint-marker so future logic
// can locate "the segment since the last compaction"; it does not
// itself extract observations from the conversation. The full
// observation-extraction workflow lives in skills/memory-checkpoint and
// requires an LLM bridge that is deferred (see docs/proposal.md / README's
// Phase 3 notes).
//
// Gated on [capture].on_pre_compact.

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { tryLoadEffectiveConfig } from "../config/loader.ts";
import { STATE_KEYS, type CheckpointMarker } from "../util/session-state.ts";

export function registerSessionBeforeCompact(pi: ExtensionAPI): void {
	pi.on("session_before_compact", async (_event, ctx) => {
		const loaded = tryLoadEffectiveConfig(ctx.cwd);
		if (!loaded.ok || !loaded.config.capture.on_pre_compact) return;

		const latestId = ctx.sessionManager.getLeafId() ?? "";
		const marker: CheckpointMarker = {
			entry_id: latestId,
			ts: new Date().toISOString(),
			mode: "pre-compact",
		};
		pi.appendEntry(STATE_KEYS.CHECKPOINT_MARKER, marker);
	});
}
