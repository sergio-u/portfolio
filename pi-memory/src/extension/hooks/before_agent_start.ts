// before_agent_start hook — injects the latest Memory Gateway content
// (basic or full, depending on what /set-context has set) into the
// system prompt for this turn.
//
// PI lets us return { systemPrompt } to REPLACE the current system
// prompt. We append the gateway content as a fenced section so the
// existing prompt stays intact and the gateway is clearly delimited.

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { readGateway } from "../util/session-state.ts";

const GATEWAY_DELIMITER_OPEN = "\n\n<!-- pi-memory gateway begin -->\n";
const GATEWAY_DELIMITER_CLOSE = "\n<!-- pi-memory gateway end -->";

export function registerBeforeAgentStart(pi: ExtensionAPI): void {
	pi.on("before_agent_start", async (event, ctx) => {
		const gateway = readGateway(ctx);
		if (!gateway) {
			// No gateway entry yet (session_start hadn't fired or config was
			// missing). Leave the system prompt as-is.
			return undefined;
		}
		const augmented =
			event.systemPrompt + GATEWAY_DELIMITER_OPEN + gateway.content + GATEWAY_DELIMITER_CLOSE;
		return { systemPrompt: augmented };
	});
}
