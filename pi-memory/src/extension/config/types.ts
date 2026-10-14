// Configuration types matching templates/config.example.toml and docs/proposal.md §5.

export interface VaultConfig {
	root: string;
	ai_folder: string;
	weekly_folder: string;
	weekly_filename: string;
	weekly_inbox: string;
	weekly_template?: string;
}

export interface CaptureConfig {
	on_pre_compact: boolean;
	on_session_shutdown: boolean;
	model: string;
	max_observations: number;
}

export interface DreamConfig {
	enabled: boolean;
	days_between: number;
	notify_on_overdue: boolean;
	max_idea_suggestions: number;
	notes_size_threshold_lines: number;
	notes_size_threshold_tokens: number;
	auto_create_domains: boolean;
	scope: string[];
}

export interface NoteConfig {
	smart_routing: boolean;
	auto_create_domains: boolean;
	multi_target: boolean;
}

export interface GatewayConfig {
	notes_tail_lines: number;
	token_budget: number;
}

export interface DumpConfig {
	group_by_day: boolean;
	include_time: boolean;
	ingest_model: string;
}

export interface OrganizeConfig {
	default_window_days: number;
	min_items_for_domain_suggestion: number;
	auto_create_domains: boolean;
	prefer_existing_domains: boolean;
	copy_not_move: boolean;
}

export type RecallMode = "grep" | "semantic" | "hybrid";

export interface AnythingLLMConfig {
	workspace: string;
	default_mode: RecallMode;
	score_threshold: number;
	top_n: number;
	host?: string; // TOML value; env ANYTHINGLLM_HOST takes precedence
	api_key?: string; // TOML value; env ANYTHINGLLM_API_KEY takes precedence
}

export interface GlobalConfig {
	vault: VaultConfig;
	capture: CaptureConfig;
	dream: DreamConfig;
	note: NoteConfig;
	gateway: GatewayConfig;
	dump: DumpConfig;
	organize: OrganizeConfig;
	anythingllm: AnythingLLMConfig;
}

export interface SentinelState {
	projects: string[];
	plan: string;
	domains: string[];
}

export interface SentinelRepo {
	name?: string;
}

export interface SentinelOverrides {
	vault?: Partial<VaultConfig>;
	capture?: Partial<CaptureConfig>;
	dream?: Partial<DreamConfig>;
	note?: Partial<NoteConfig>;
	gateway?: Partial<GatewayConfig>;
	dump?: Partial<DumpConfig>;
	organize?: Partial<OrganizeConfig>;
	anythingllm?: Partial<AnythingLLMConfig>;
}

export interface SentinelConfig {
	repo: SentinelRepo;
	state: SentinelState;
	overrides: SentinelOverrides;
}

// What the rest of the extension actually consumes: global merged with
// sentinel overrides + state + repo info attached.
export interface EffectiveConfig extends GlobalConfig {
	repo: SentinelRepo;
	state: SentinelState;
}

// Defaults applied when keys are missing from the global config file.
export const DEFAULT_CONFIG: GlobalConfig = {
	vault: {
		root: "",
		ai_folder: "80_AI",
		weekly_folder: "10_Weekly",
		weekly_filename: "%Y-W%V",
		weekly_inbox: "## Inbox",
	},
	capture: {
		on_pre_compact: true,
		on_session_shutdown: true,
		model: "default",
		max_observations: 3,
	},
	dream: {
		enabled: true,
		days_between: 15,
		notify_on_overdue: true,
		max_idea_suggestions: 5,
		notes_size_threshold_lines: 500,
		notes_size_threshold_tokens: 20000,
		auto_create_domains: true,
		scope: ["80_AI", "10_Weekly"],
	},
	note: {
		smart_routing: true,
		auto_create_domains: false,
		multi_target: true,
	},
	gateway: {
		notes_tail_lines: 50,
		token_budget: 5000,
	},
	dump: {
		group_by_day: true,
		include_time: false,
		ingest_model: "default",
	},
	organize: {
		default_window_days: 30,
		min_items_for_domain_suggestion: 3,
		auto_create_domains: false,
		prefer_existing_domains: true,
		copy_not_move: true,
	},
	anythingllm: {
		workspace: "my-workspace",
		default_mode: "grep",
		score_threshold: 0.2,
		top_n: 8,
	},
};

export const EMPTY_SENTINEL: SentinelConfig = {
	repo: {},
	state: { projects: [], plan: "", domains: [] },
	overrides: {},
};
