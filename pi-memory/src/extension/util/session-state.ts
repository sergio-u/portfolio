// Helpers for reading/writing transient session state via custom entries.
//
// We use a small set of customType values to track in-session state that
// shouldn't persist to disk:
//
//   memory-gateway                  { level, content, ts }
//   memory-checkpoint-marker        { entry_id, ts, mode? }
//
// `pi.appendEntry(customType, data)` writes; reading is via the
// active session branch filtered by type/customType. The latest entry on
// the active path wins; entries on abandoned /tree branches are ignored.

import type { ExtensionContext } from "@earendil-works/pi-coding-agent";

export interface GatewayEntry {
	level: "basic" | "full";
	content: string;
	ts: string;
}

export interface CheckpointMarker {
	entry_id: string;
	ts: string;
	mode?: "pre-compact" | "shutdown" | "manual";
}

export const STATE_KEYS = {
	GATEWAY: "memory-gateway",
	CHECKPOINT_MARKER: "memory-checkpoint-marker",
} as const;

/**
 * Walk session entries newest-first and return the data of the latest
 * "custom" entry matching the given customType. Returns null if none.
 */
export function readLatestCustomEntry<T>(
	ctx: ExtensionContext,
	customType: string,
): T | null {
	const entries = ctx.sessionManager.getBranch();
	for (let i = entries.length - 1; i >= 0; i--) {
		const e = entries[i];
		// `type` and `customType` are present on CustomEntry; narrow via a
		// shape check to avoid coupling to PI's internal entry-type names.
		if ((e as { type?: string }).type === "custom") {
			const ce = e as { type: "custom"; customType?: string; data?: unknown };
			if (ce.customType === customType) {
				return (ce.data as T | undefined) ?? null;
			}
		}
	}
	return null;
}

export function readGateway(ctx: ExtensionContext): GatewayEntry | null {
	return readLatestCustomEntry<GatewayEntry>(ctx, STATE_KEYS.GATEWAY);
}

export function readCheckpointMarker(ctx: ExtensionContext): CheckpointMarker | null {
	return readLatestCustomEntry<CheckpointMarker>(ctx, STATE_KEYS.CHECKPOINT_MARKER);
}
