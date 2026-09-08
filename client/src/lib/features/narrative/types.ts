export type NarrativeGraph = {
	id: string;
	name: string;
	version: number;
	created_at: string | null;
	updated_at: string | null;
};
export type TipTapDocument = Record<string, unknown>;
export type StoryChapter = {
	id: string;
	graph_id: string;
	title: string;
	sequence: number;
	revision: number;
	document: TipTapDocument;
	plain_text: string;
};
export type AnalysisRun = {
	id: string;
	graph_id: string;
	chapter_id: string;
	chapter_revision: number;
	status: string;
	error: string | null;
};
export type AnalysisProposal = {
	id: string;
	operation_type: string;
	payload: {
		operations: Array<{ id: string; operation_type: string; payload: Record<string, unknown> }>;
	};
	provenance: Record<string, unknown>;
	status: 'proposed' | 'accepted' | 'rejected';
};
export type TextProposal = {
	id: string;
	text: string;
	rationale: string;
};
export type AgentGroup =
	'analysis' | 'draft' | 'review' | 'research' | 'visuals' | 'voice' | 'produce';
export type AgentRun = {
	id: string;
	graph_id: string;
	chapter_id: string | null;
	agent_group: AgentGroup;
	scope: 'chapter' | 'story';
	status: 'queued' | 'running' | 'completed' | 'failed' | 'reviewed';
	progress: number;
	message: string;
	error: string | null;
	result: {
		stages?: string[];
		text_patches?: TextProposal[];
		graph_proposals?: AnalysisProposal[];
		findings?: Array<{ severity: string; message: string; suggestion?: string }>;
		report?: {
			verdict?: string;
			confidence_score?: number;
			era_analyzed?: string;
			historical_summary?: string;
			detected_anachronisms?: Array<{
				element?: string;
				issue?: string;
				periodAccurateAlternative?: string;
			}>;
			recommendations_for_writers?: string;
			search_sources?: Array<{ title?: string; url?: string; excerpts?: string[] }>;
			[key: string]: unknown;
		};
		artifact_ids?: string[];
		story_title?: string;
		story_text?: string;
		chapters?: Array<{ id: string; title: string; sequence: number }>;
		visual?: {
			scene_id?: string;
			chapter_title?: string;
			image_url?: string | null;
			image_path?: string | null;
			scenes?: Array<{
				scene_id: string;
				title: string;
				header: string;
				excerpt: string;
				image_url?: string | null;
			}>;
		};
		stored_scene_ids?: string[];
		media?: {
			image_url?: string | null;
			image_path?: string | null;
			storyboards?: Array<{
				scene_id: string;
				title: string;
				header: string;
				excerpt: string;
				image_url?: string | null;
			}>;
			dialogues?: Array<{ speaker: string; line: string; audio_url?: string | null }>;
		};
		dialogues?: {
			dialogues?: Array<{ speaker: string; line: string; audio_url?: string | null }>;
		};
		pdf_path?: string | null;
		[key: string]: unknown;
	};
};
export type OperationBatch = {
	id: string;
	graph_id: string;
	status: string;
	operation_count: number;
	error: string | null;
};
export type NarrativeRecord = Record<string, unknown>;
export type Subgraph = {
	graph_id: string;
	viewpoint_entity_id: string | null;
	entities: NarrativeRecord[];
	contexts: NarrativeRecord[];
	events: NarrativeRecord[];
	knowledge_elements: NarrativeRecord[];
	statements: NarrativeRecord[];
	relations: NarrativeRecord[];
	evidence: NarrativeRecord[];
};
