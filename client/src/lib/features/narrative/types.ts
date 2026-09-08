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
