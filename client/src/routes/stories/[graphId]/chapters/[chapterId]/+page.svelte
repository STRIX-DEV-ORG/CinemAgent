<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { onDestroy, untrack } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Toggle } from '$lib/components/ui/toggle';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import { Textarea } from '$lib/components/ui/textarea';
	import * as Dialog from '$lib/components/ui/dialog';
	import { narrativeApi, workspaceApi } from '$lib/features/narrative/api';
	import { contextTypeOptions, entityTypeOptions, eventTypeOptions } from '$lib/features/narrative/node-options';
	import type {
		AnalysisProposal,
		AgentGroup,
		AgentRun,
		StoryChapter,
		Subgraph,
		TextProposal,
		TipTapDocument
	} from '$lib/features/narrative/types';
	import ChapterEditor from '$lib/components/workspace/chapter-editor.svelte';
	import NarrativeCanvas from '$lib/components/workspace/narrative-canvas.svelte';
	import ToolToggle from '$lib/components/workspace/tool-toggle.svelte';
	import NodeCreateSidebar from '$lib/components/workspace/node-create-sidebar.svelte';
	import StoryMenu from '$lib/components/workspace/story-menu.svelte';
	import { BrainCircuit, PenTool, ClipboardCheck, Search, Image as ImageIcon, Mic, Film, Loader2, CircleHelp } from 'lucide-svelte';

	let { params } = $props();
	let chapter = $state<StoryChapter | null>(null);
	let chapters = $state<StoryChapter[]>([]);
	let chapterTitleDraft = $state('');
	let editingChapterTitle = $state(false);
	let savingChapterTitle = $state(false);
	let subgraph = $state<Subgraph | null>(null);
	let proposals = $state<AnalysisProposal[]>([]);
	let selectedProposalIds = $state<string[]>([]);
	let applyingProposals = $state(false);
	let proposalSource = $state<'analysis' | 'review' | null>(null);
	let selectedLabel = $state('');
	let selectedRecord = $state<Record<string, unknown> | null>(null);
	let selectedNodeKind = $state<'entity' | 'event' | 'context' | 'knowledge_element' | null>(null);
	let saveState = $state<'saved' | 'saving' | 'error'>('saved');
	let message = $state('');
	let chapterQuery = $state('');
	let chapterPickerOpen = $state(false);
	let deleteDialogOpen = $state(false);
	let deletingChapter = $state(false);
	let deleteNodeDialogOpen = $state(false);
	let deletingNode = $state(false);
	let editNodeDialogOpen = $state(false);
	let savingNode = $state(false);
	let nodeFormName = $state('');
	let nodeFormType = $state('');
	let nodeFormStatus = $state('active');
	let nodeFormDescription = $state('');
	let nodeFormContent = $state('');
	let nodeFormAliases = $state('');
	let nodeFormHolder = $state('');
	let nodeFormOrigin = $state('writer');
	let nodeFormConfidence = $state('1');
	let metadataEntries = $state<Array<{ key: string; value: string }>>([{ key: '', value: '' }]);
	let preservedMetadata = $state<Record<string, unknown>>({});
	let analyzing = $state(false);
	let proposingText = $state(false);
	let agentRunning = $state<AgentGroup | null>(null);
	let agentRuns = $state<AgentRun[]>([]);
	let agentOutput = $state<AgentRun | null>(null);
	let agentResultsOpen = $state(false);
	let storyboardReviewOpen = $state(false);
	let storyboardIndex = $state(0);
	let selectedStoryboardIds = $state<string[]>([]);
	let savingStoryboards = $state(false);
	let textProposals = $state<TextProposal[]>([]);
	let nodeSidebarOpen = $state(false);
	let creatingNode = $state(false);
	let relationDialogOpen = $state(false);
	let creatingRelation = $state(false);
	let relationType = $state<'statement' | 'context'>('statement');
	let relationLabel = $state('related_to');
	let customRelationLabel = $state('');
	let relationDescription = $state('');
	let relationConfidence = $state('1');
	let editingRelationId = $state<string | null>(null);
	let deleteRelationDialogOpen = $state(false);
	let deletingRelation = $state(false);
	let loading = $state(true);
	let loadVersion = 0;
	let pendingRelation = $state<{
		sourceId: string;
		targetId: string;
		sourceLabel: string;
		targetLabel: string;
		hasContext: boolean;
	} | null>(null);
	let existingNodes = $state<
		Array<{
			id: string;
			label: string;
			nodeType: 'entity' | 'event' | 'context' | 'knowledge_element';
		}>
	>([]);
	let saveTimer: ReturnType<typeof setTimeout> | undefined;
	let runId = $state<string | null>(null);
	const selection = $derived(page.url.searchParams.get('node'));
	const matchingChapters = $derived(
		chapters.filter((storyChapter) =>
			`${storyChapter.sequence}. ${storyChapter.title}`
				.toLocaleLowerCase()
				.includes(chapterQuery.trim().toLocaleLowerCase())
		)
	);
	const currentChapterIndex = $derived(chapters.findIndex((item) => item.id === params.chapterId));
	const previousChapter = $derived(
		currentChapterIndex > 0 ? chapters[currentChapterIndex - 1] : undefined
	);
	const nextChapter = $derived(
		currentChapterIndex >= 0 && currentChapterIndex < chapters.length - 1
			? chapters[currentChapterIndex + 1]
			: undefined
	);
	const researchScope = $derived(
		(agentOutput?.result.report?.research_scope ?? {}) as Record<string, unknown>
	);
	const generatedStoryboardScenes = $derived.by(() => {
		const scenes = agentOutput?.result.media?.storyboards ?? agentOutput?.result.visual?.scenes;
		if (scenes?.length) return scenes;
		const visual = agentOutput?.result.visual;
		if (visual?.image_url || visual?.image_path) {
			return [{
				scene_id: visual.scene_id ?? agentOutput?.id ?? 'storyboard',
				title: visual.chapter_title ?? chapter?.title ?? 'Storyboard scene',
				header: 'CHAPTER STORYBOARD',
				excerpt: 'A generated storyboard image for this chapter.',
				image_url: visual.image_url ?? visual.image_path
			}];
		}
		return [];
	});
	const storedStoryboardScenes = $derived.by(() => {
		const storedIds = agentOutput?.result.stored_scene_ids;
		return agentOutput?.status === 'reviewed' && storedIds
			? generatedStoryboardScenes.filter((scene) => storedIds.includes(scene.scene_id))
			: generatedStoryboardScenes;
	});
	const currentStoryboardScene = $derived(generatedStoryboardScenes[storyboardIndex]);
	function mediaUrl(url: string | null | undefined): string {
		if (!url) return '';
		const mediaPrefix = '/api/v1/pipeline/media/';
		const mediaIndex = url.indexOf(mediaPrefix);
		return mediaIndex >= 0
			? `/api/media/${encodeURIComponent(url.slice(mediaIndex + mediaPrefix.length))}`
			: url;
	}
	const selectedRelations = $derived.by(() => {
		if (!selectedRecord || !subgraph) return [];
		const selectedId = String(selectedRecord.id);
		const records = [
			...subgraph.entities.map((record) => ({ record, kind: 'entity' })),
			...subgraph.events.map((record) => ({ record, kind: 'event' })),
			...subgraph.contexts.map((record) => ({ record, kind: 'context' })),
			...subgraph.knowledge_elements.map((record) => ({ record, kind: 'knowledge' }))
		];
		const recordById = new Map(records.map((item) => [String(item.record.id), item]));
		const relationIds = new Set((subgraph.relations ?? []).map((relation) => String(relation.id)));
		const relations = [
			...(subgraph.relations ?? []),
			...subgraph.statements
				.filter((statement) => !relationIds.has(String(statement.id)))
				.map((statement) => ({
					id: statement.id,
					source_node_id: statement.subject_entity_id,
					target_node_id: statement.object_entity_id,
					relation_type: 'statement',
					label: statement.predicate,
					description: statement.description
				}))
		];
		return relations
			.filter(
				(relation) =>
					String(relation.source_node_id) === selectedId ||
					String(relation.target_node_id) === selectedId
			)
			.map((relation) => {
				const outgoing = String(relation.source_node_id) === selectedId;
				const otherId = String(outgoing ? relation.target_node_id : relation.source_node_id);
				const other = recordById.get(otherId);
				return {
					id: String(relation.id),
					outgoing,
					label: String(relation.label ?? 'related_to').replaceAll('_', ' '),
					description: String(relation.description ?? ''),
					relationType: String(relation.relation_type ?? 'statement'),
					otherId,
					otherLabel: other
						? String(other.record.name ?? other.record.type ?? other.record.element_type ?? otherId)
						: otherId,
					otherKind: other?.kind,
					otherRecord: other?.record
				};
			});
	});

	async function load(graphId = params.graphId, chapterId = params.chapterId) {
		const version = ++loadVersion;
		loading = true;
		message = '';
		try {
			const [loadedChapter, loadedSubgraph, loadedChapters, loadedRuns] = await Promise.all([
				workspaceApi.getChapter(graphId, chapterId),
				narrativeApi.querySubgraph(graphId, false, [], chapterId),
				workspaceApi.listChapters(graphId),
				workspaceApi.listAgentRuns(graphId, chapterId)
			]);
			if (version !== loadVersion) return;
			chapter = loadedChapter;
			subgraph = loadedSubgraph;
			chapters = loadedChapters;
			agentRuns = loadedRuns;
			chapterQuery = chapter.title;
			chapterTitleDraft = chapter.title;
		} catch (error) {
			if (version !== loadVersion) return;
			message = error instanceof Error ? error.message : 'Could not load chapter.';
		} finally {
			if (version === loadVersion) loading = false;
		}
	}
	$effect(() => {
		const graphId = params.graphId;
		const chapterId = params.chapterId;
		untrack(() => void load(graphId, chapterId));
	});
	$effect(() => {
		const visibleMessage = message;
		if (!visibleMessage) return;
		const timer = setTimeout(() => {
			if (message === visibleMessage) message = '';
		}, 6000);
		return () => clearTimeout(timer);
	});
	onDestroy(() => {
		if (saveTimer) clearTimeout(saveTimer);
	});
	function scheduleSave(document: TipTapDocument, plainText: string) {
		if (!chapter) return;
		if (saveTimer) clearTimeout(saveTimer);
		saveState = 'saving';
		saveTimer = setTimeout(async () => {
			try {
				chapter = await workspaceApi.saveDocument(
					params.graphId,
					params.chapterId,
					document,
					plainText,
					chapter!.revision
				);
				saveState = 'saved';
			} catch (error) {
				saveState = 'error';
				message = error instanceof Error ? error.message : 'Could not save chapter.';
			}
		}, 700);
	}
	async function analyze() {
		if (!chapter) return;
		if (saveState === 'saving') {
			message = 'Your chapter is still saving. Try analysis again in a moment.';
			return;
		}
		analyzing = true;
		try {
			const run = await workspaceApi.startAnalysis(params.graphId, params.chapterId);
			runId = run.id;
			proposals = await workspaceApi.getProposals(params.graphId, params.chapterId, run.id);
			proposalSource = 'analysis';
			selectedProposalIds = proposals
				.filter((proposal) => proposal.status === 'proposed')
				.map((proposal) => proposal.id);
			message = proposals.length
				? `${proposals.length} graph proposals were extracted from this draft. Review them before applying.`
				: 'No clear entities, events, or settings were found in this draft yet.';
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not analyze chapter.';
		} finally {
			analyzing = false;
		}
	}
	async function proposeTextFromGraph() {
		if (!chapter) return;
		if (saveState === 'saving') {
			message = 'Your latest edits are still saving. Try again in a moment.';
			return;
		}
		proposingText = true;
		try {
			textProposals = await workspaceApi.suggestText(params.graphId, params.chapterId);
			message = textProposals.length
				? `${textProposals.length} graph-grounded prose suggestions are ready for review.`
				: 'The current draft already covers the available chapter graph details.';
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not create text proposals.';
		} finally {
			proposingText = false;
		}
	}
	async function runAgent(group: AgentGroup) {
		if (!chapter || agentRunning) return;
		agentRunning = group;
		try {
			let run = await workspaceApi.startAgentRun(params.graphId, {
				agent_group: group,
				chapter_id: params.chapterId,
				scope: 'chapter'
			});
			for (
				let attempt = 0;
				attempt < 60 && ['queued', 'running'].includes(run.status);
				attempt += 1
			) {
				await new Promise((resolve) => setTimeout(resolve, 500));
				run = await workspaceApi.getAgentRun(params.graphId, run.id);
			}
			agentOutput = run;
			agentResultsOpen = group === 'review' || group === 'research';
			agentRuns = [run, ...agentRuns.filter((item) => item.id !== run.id)].slice(0, 12);
			if (run.status === 'failed') throw new Error(run.error || 'The agent run failed.');
			if (run.result.graph_proposals) {
				proposals = run.result.graph_proposals;
				proposalSource = group === 'review' ? 'review' : 'analysis';
				runId = String(run.result.analysis_run_id ?? '');
				selectedProposalIds = proposals
					.filter((proposal) => proposal.status === 'proposed')
					.map((proposal) => proposal.id);
			}
			if (run.result.text_patches) textProposals = run.result.text_patches;
			const visualScenes = run.result.visual?.scenes?.length
				? run.result.visual.scenes
				: run.result.visual?.image_url || run.result.visual?.image_path
					? [{ scene_id: run.result.visual.scene_id ?? run.id }]
					: [];
			if (group === 'visuals' && visualScenes.length) {
				storyboardIndex = 0;
				selectedStoryboardIds = visualScenes.map((scene) => scene.scene_id);
				storyboardReviewOpen = true;
			}
			message = `${group.replace('_', ' ')} is ready for review.`;
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not run this AI tool.';
		} finally {
			agentRunning = null;
		}
	}
	function toggleStoryboardSelection(sceneId: string) {
		selectedStoryboardIds = selectedStoryboardIds.includes(sceneId)
			? selectedStoryboardIds.filter((id) => id !== sceneId)
			: [...selectedStoryboardIds, sceneId];
	}
	async function storeSelectedStoryboards() {
		if (!agentOutput || !selectedStoryboardIds.length || savingStoryboards) return;
		savingStoryboards = true;
		try {
			const updated = await workspaceApi.saveStoryboards(
				params.graphId,
				agentOutput.id,
				selectedStoryboardIds
			);
			agentOutput = updated;
			agentRuns = [updated, ...agentRuns.filter((item) => item.id !== updated.id)].slice(0, 12);
			storyboardReviewOpen = false;
			message = `${selectedStoryboardIds.length} storyboard image(s) saved to this chapter.`;
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not save storyboard images.';
		} finally {
			savingStoryboards = false;
		}
	}
	async function discardStoryboards() {
		if (!agentOutput || savingStoryboards) return;
		// Closing is a local UI decision. Persist it when the current API has
		// the storyboard endpoint, but never trap the writer in this modal.
		storyboardReviewOpen = false;
		selectedStoryboardIds = [];
		savingStoryboards = true;
		try {
			const updated = await workspaceApi.saveStoryboards(params.graphId, agentOutput.id, []);
			agentOutput = updated;
			agentRuns = [updated, ...agentRuns.filter((item) => item.id !== updated.id)].slice(0, 12);
			message = 'Generated storyboard images were discarded.';
		} catch (error) {
			message = 'Storyboard review closed. The current API must be restarted before discard decisions can be recorded.';
		} finally {
			savingStoryboards = false;
		}
	}
	async function applyTextProposal(proposal: { id: string; text: string }) {
		if (!chapter || saveState === 'saving') return;
		const existingContent = Array.isArray(chapter.document.content) ? chapter.document.content : [];
		const document: TipTapDocument = {
			...chapter.document,
			type: 'doc',
			content: [
				...existingContent,
				{ type: 'paragraph', content: [{ type: 'text', text: proposal.text }] }
			]
		};
		const plainText = [chapter.plain_text, proposal.text].filter(Boolean).join('\n\n');
		saveState = 'saving';
		try {
			chapter = await workspaceApi.saveDocument(
				params.graphId,
				params.chapterId,
				document,
				plainText,
				chapter.revision
			);
			textProposals = textProposals.filter((item) => item.id !== proposal.id);
			saveState = 'saved';
			message = 'Text proposal added to the chapter.';
		} catch (error) {
			saveState = 'error';
			message = error instanceof Error ? error.message : 'Could not apply text proposal.';
		}
	}
	async function acceptAgentPatches() {
		if (!agentOutput?.result.text_patches?.length) return;
		try {
			agentOutput = await workspaceApi.reviewAgentRun(
				params.graphId,
				agentOutput.id,
				agentOutput.result.text_patches.map((patch) => patch.id)
			);
			await load();
			textProposals = [];
			message = 'Accepted text suggestions were added to the chapter.';
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not apply the reviewed text.';
		}
	}
	async function apply() {
		if (!proposals.length || !runId || !selectedProposalIds.length || applyingProposals) return;
		applyingProposals = true;
		message = `Adding ${selectedProposalIds.length} graph proposal(s)…`;
		try {
			const batch = await workspaceApi.applyProposals(
				params.graphId,
				params.chapterId,
				runId,
				selectedProposalIds
			);
			message = `Applying ${selectedProposalIds.length} graph proposal(s)…`;
			const completed = await waitForBatch(batch.id);
			if (completed.status !== 'applied') {
				throw new Error(completed.error || `Graph proposals ${completed.status}.`);
			}
			proposals = [];
			runId = null;
			proposalSource = null;
			await load();
			message = 'Graph proposals applied.';
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not apply graph proposals.';
		} finally {
			applyingProposals = false;
		}
	}
	function dismissGraphProposals() {
		if (applyingProposals || !proposals.length) return;
		const dismissedCount = proposals.length;
		proposals = [];
		selectedProposalIds = [];
		runId = null;
		proposalSource = null;
		message = `${dismissedCount} graph proposal(s) dismissed. Nothing was added to the graph.`;
	}
	function dismissAgentResults() {
		agentResultsOpen = false;
		storyboardReviewOpen = false;
		agentOutput = null;
	}
	function proposalSummary(proposal: AnalysisProposal) {
		return String(
			proposal.provenance.summary ?? `Create ${proposal.operation_type.replaceAll('_', ' ')}`
		);
	}
	function proposalExcerpt(proposal: AnalysisProposal) {
		return typeof proposal.provenance.excerpt === 'string' ? proposal.provenance.excerpt : '';
	}
	function selectNode(id: string, label: string, kind: string, record: Record<string, unknown>) {
		selectedLabel = label;
		selectedRecord = record;
		selectedNodeKind =
			kind === 'knowledge' ? 'knowledge_element' : (kind as typeof selectedNodeKind);
		openNodeEditor(false);
		goto(resolve(`/stories/${params.graphId}/chapters/${params.chapterId}?node=${id}`));
		void refreshFocusedGraph(id);
	}
	async function refreshFocusedGraph(entityId: string) {
		try {
			subgraph = await narrativeApi.querySubgraph(
				params.graphId,
				false,
				[entityId],
				params.chapterId
			);
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not focus the graph.';
		}
	}
	function openChapterTimeline() {
		void goto(resolve(`/stories/${params.graphId}`));
	}
	async function clearNodeSelection() {
		selectedLabel = '';
		selectedRecord = null;
		selectedNodeKind = null;
		await goto(resolve(`/stories/${params.graphId}/chapters/${params.chapterId}`));
		subgraph = await narrativeApi.querySubgraph(params.graphId, false, [], params.chapterId);
	}
	function selectChapter(storyChapter: StoryChapter) {
		chapterQuery = storyChapter.title;
		chapterPickerOpen = false;
		void goto(resolve(`/stories/${params.graphId}/chapters/${storyChapter.id}`));
	}
	function startEditingChapterTitle() {
		chapterTitleDraft = chapter?.title ?? '';
		editingChapterTitle = true;
	}
	async function saveChapterTitle() {
		if (!chapter || !chapterTitleDraft.trim()) return;
		savingChapterTitle = true;
		try {
			chapter = await workspaceApi.updateChapter(params.graphId, params.chapterId, {
				title: chapterTitleDraft.trim()
			});
			chapters = chapters.map((item) => (item.id === chapter!.id ? chapter! : item));
			chapterQuery = chapter.title;
			editingChapterTitle = false;
			message = 'Chapter title updated.';
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not update chapter title.';
		} finally {
			savingChapterTitle = false;
		}
	}
	async function deleteCurrentChapter() {
		if (!chapter || chapters.length <= 1) return;
		deletingChapter = true;
		try {
			await workspaceApi.deleteChapter(params.graphId, params.chapterId);
			deleteDialogOpen = false;
			await goto(resolve(`/stories/${params.graphId}`));
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not delete chapter.';
		} finally {
			deletingChapter = false;
		}
	}
	async function deleteSelectedNode() {
		if (!selectedRecord || !selectedNodeKind) return;
		deletingNode = true;
		try {
			const batch = await narrativeApi.deleteNode(
				params.graphId,
				String(selectedRecord.id),
				selectedNodeKind
			);
			message = `Graph delete ${(await waitForBatch(batch.id)).status}.`;
			deleteNodeDialogOpen = false;
			selectedLabel = '';
			selectedRecord = null;
			selectedNodeKind = null;
			await goto(resolve(`/stories/${params.graphId}/chapters/${params.chapterId}`));
			subgraph = await narrativeApi.querySubgraph(params.graphId, false, [], params.chapterId);
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not delete graph element.';
		} finally {
			deletingNode = false;
		}
	}
	function openNodeEditor(showDialog = true) {
		if (!selectedRecord || !selectedNodeKind) return;
		nodeFormName = String(selectedRecord.name ?? '');
		nodeFormType = String(selectedRecord.type ?? selectedRecord.element_type ?? '');
		nodeFormStatus = String(selectedRecord.status ?? 'active');
		nodeFormDescription = String(selectedRecord.description ?? '');
		nodeFormContent = String(selectedRecord.content ?? '');
		nodeFormAliases = Array.isArray(selectedRecord.aliases)
			? selectedRecord.aliases.join(', ')
			: '';
		nodeFormHolder = String(selectedRecord.holder_entity_id ?? '');
		nodeFormOrigin = String(selectedRecord.origin ?? 'writer');
		nodeFormConfidence = String(selectedRecord.confidence ?? 1);
		const existingMetadata =
			selectedRecord.metadata && typeof selectedRecord.metadata === 'object'
				? (selectedRecord.metadata as Record<string, unknown>)
				: {};
		preservedMetadata = Object.fromEntries(
			Object.entries(existingMetadata).filter(
				([key, value]) => key === 'chapter_id' || value === null || typeof value === 'object'
			)
		);
		metadataEntries = Object.entries(existingMetadata)
			.filter(([key, value]) => key !== 'chapter_id' && value !== null && typeof value !== 'object')
			.map(([key, value]) => ({ key, value: String(value) }));
		if (!metadataEntries.length) metadataEntries = [{ key: '', value: '' }];
		editNodeDialogOpen = showDialog;
	}
	async function saveNodeEdits() {
		const record = selectedRecord;
		const nodeType = selectedNodeKind;
		if (!record || !nodeType) return;
		const metadata: Record<string, unknown> = { ...preservedMetadata };
		for (const entry of metadataEntries) {
			const key = entry.key.trim();
			if (key) metadata[key] = entry.value.trim();
		}
		const confidence = Number(nodeFormConfidence);
		if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
			message = 'Confidence must be a number from 0 to 1.';
			return;
		}
		const changes: Record<string, unknown> = { confidence, metadata, content: nodeFormContent };
		if (nodeType === 'entity') {
			Object.assign(changes, {
				name: nodeFormName.trim(),
				type: nodeFormType.trim(),
				status: nodeFormStatus,
				description: nodeFormDescription,
				aliases: nodeFormAliases
					.split(',')
					.map((alias) => alias.trim())
					.filter(Boolean)
			});
		} else if (nodeType === 'event') {
			Object.assign(changes, {
				name: nodeFormName.trim(),
				type: nodeFormType.trim(),
				status: nodeFormStatus,
				description: nodeFormDescription
			});
		} else if (nodeType === 'context') {
			Object.assign(changes, {
				name: nodeFormName.trim(),
				type: nodeFormType.trim(),
				description: nodeFormDescription,
				holder_entity_id: nodeFormHolder.trim() || null
			});
		} else {
			Object.assign(changes, {
				name: nodeFormName.trim(),
				element_type: nodeFormType.trim(),
				description: nodeFormDescription,
				origin: nodeFormOrigin.trim(),
				status: nodeFormStatus
			});
		}
		savingNode = true;
		try {
			const batch = await narrativeApi.updateNode(
				params.graphId,
				String(record.id),
				nodeType,
				changes
			);
			message = `Graph update ${(await waitForBatch(batch.id)).status}.`;
			editNodeDialogOpen = false;
			selectedRecord = { ...record, ...changes };
			if (typeof changes.name === 'string') selectedLabel = changes.name;
			else if (typeof changes.type === 'string') selectedLabel = changes.type;
			else if (typeof changes.element_type === 'string') selectedLabel = changes.element_type;
			subgraph = await narrativeApi.querySubgraph(params.graphId, false, [], params.chapterId);
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not update graph element.';
		} finally {
			savingNode = false;
		}
	}
	async function createNode(
		kind: 'entity' | 'event' | 'context' | 'assumption',
		values: Record<string, unknown>
	) {
		creatingNode = true;
		try {
			const batch = await narrativeApi.createNode(params.graphId, kind, values, params.chapterId);
			message = `Graph write ${(await waitForBatch(batch.id)).status}.`;
			nodeSidebarOpen = false;
			await load();
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not create graph element.';
		} finally {
			creatingNode = false;
		}
	}
	async function openNodeSidebar() {
		nodeSidebarOpen = true;
		try {
			const graph = await narrativeApi.querySubgraph(params.graphId, false);
			const current = new Set(
				[
					...(subgraph?.entities ?? []),
					...(subgraph?.events ?? []),
					...(subgraph?.contexts ?? []),
					...(subgraph?.knowledge_elements ?? [])
				].map((node) => String(node.id))
			);
			existingNodes = [
				...graph.entities.map((node) => ({
					id: String(node.id),
					label: String(node.name),
					nodeType: 'entity' as const
				})),
				...graph.events.map((node) => ({
					id: String(node.id),
					label: String(node.name),
					nodeType: 'event' as const
				})),
				...graph.contexts.map((node) => ({
					id: String(node.id),
					label: String(node.type),
					nodeType: 'context' as const
				})),
				...graph.knowledge_elements
					.filter((node) => node.element_type !== 'statement')
					.map((node) => ({
						id: String(node.id),
						label: String(node.element_type),
						nodeType: 'knowledge_element' as const
					}))
			].filter((node) => !current.has(node.id));
		} catch (error) {
			existingNodes = [];
			message = error instanceof Error ? error.message : 'Could not load existing story nodes.';
		}
	}
	async function linkExistingNode(
		id: string,
		nodeType: 'entity' | 'event' | 'context' | 'knowledge_element'
	) {
		creatingNode = true;
		try {
			const batch = await narrativeApi.linkNodeToChapter(
				params.graphId,
				params.chapterId,
				id,
				nodeType
			);
			message = `Node added ${(await waitForBatch(batch.id)).status}.`;
			await load();
			await openNodeSidebar();
		} finally {
			creatingNode = false;
		}
	}
	function beginRelation(sourceId: string, targetId: string) {
		if (sourceId === targetId) return;
		const records = [
			...(subgraph?.entities ?? []).map((record) => ({ record, kind: 'entity' })),
			...(subgraph?.events ?? []).map((record) => ({ record, kind: 'event' })),
			...(subgraph?.contexts ?? []).map((record) => ({ record, kind: 'context' })),
			...(subgraph?.knowledge_elements ?? []).map((record) => ({ record, kind: 'knowledge' }))
		];
		const source = records.find(({ record }) => String(record.id) === sourceId);
		const target = records.find(({ record }) => String(record.id) === targetId);
		if (!source || !target) {
			message = 'Both ends of the relation must be visible in this chapter.';
			return;
		}
		pendingRelation = {
			sourceId,
			targetId,
			sourceLabel: String(
				source.record.name ?? source.record.type ?? source.record.element_type ?? sourceId
			),
			targetLabel: String(
				target.record.name ?? target.record.type ?? target.record.element_type ?? targetId
			),
			hasContext: source.kind === 'context' || target.kind === 'context'
		};
		relationType = 'statement';
		relationLabel = 'related_to';
		customRelationLabel = '';
		relationDescription = '';
		relationConfidence = '1';
		editingRelationId = null;
		relationDialogOpen = true;
	}
	function relationNodes() {
		return [
			...(subgraph?.entities ?? []).map((record) => ({ id: String(record.id), label: String(record.name ?? record.id), kind: 'entity' })),
			...(subgraph?.events ?? []).map((record) => ({ id: String(record.id), label: String(record.name ?? record.type ?? record.id), kind: 'event' })),
			...(subgraph?.contexts ?? []).map((record) => ({ id: String(record.id), label: String(record.type ?? record.id), kind: 'context' })),
			...(subgraph?.knowledge_elements ?? []).filter((record) => record.element_type !== 'statement').map((record) => ({ id: String(record.id), label: String(record.element_type ?? record.id), kind: 'knowledge' }))
		];
	}
	function setRelationEndpoint(endpoint: 'source' | 'target', id: string) {
		if (!pendingRelation) return;
		const nodes = relationNodes();
		const sourceId = endpoint === 'source' ? id : pendingRelation.sourceId;
		const targetId = endpoint === 'target' ? id : pendingRelation.targetId;
		const source = nodes.find((node) => node.id === sourceId);
		const target = nodes.find((node) => node.id === targetId);
		if (!source || !target || sourceId === targetId) return;
		pendingRelation = {
			sourceId,
			targetId,
			sourceLabel: source.label,
			targetLabel: target.label,
			hasContext: source.kind === 'context' || target.kind === 'context'
		};
	}
	function editRelation(relation: Record<string, unknown>) {
		const sourceId = String(relation.source_node_id);
		const targetId = String(relation.target_node_id);
		beginRelation(sourceId, targetId);
		editingRelationId = String(relation.id);
		relationType = String(relation.relation_type) === 'context' ? 'context' : 'statement';
		const label = String(relation.label ?? 'related_to');
		const knownLabels = relationType === 'statement'
			? ['related_to', 'knows', 'trusts', 'supports', 'opposes', 'owns', 'seeks', 'located_in', 'participates_in', 'causes', 'precedes']
			: ['takes_place_in', 'applies_in', 'viewed_through', 'governed_by'];
		relationLabel = knownLabels.includes(label) ? label : 'custom';
		customRelationLabel = relationLabel === 'custom' ? label : '';
		relationDescription = String(relation.description ?? '');
		relationConfidence = String(relation.confidence ?? 1);
	}
	function changeRelationType(next: 'statement' | 'context') {
		relationType = next;
		relationLabel = next === 'statement' ? 'related_to' : 'takes_place_in';
		customRelationLabel = '';
	}
	async function createRelation() {
		const label = relationLabel === 'custom' ? customRelationLabel.trim() : relationLabel;
		if (!pendingRelation || !label) {
			message = 'Give this relation a meaningful label before saving it.';
			return;
		}
		if (relationType === 'context' && !pendingRelation.hasContext) {
			message = 'A contextual relation must connect to a context node.';
			return;
		}
		const confidence = Number(relationConfidence);
		if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
			message = 'Confidence must be a number from 0 to 1.';
			return;
		}
		creatingRelation = true;
		try {
			const batch = editingRelationId
				? await narrativeApi.updateRelation(params.graphId, editingRelationId, {
						source_node_id: pendingRelation.sourceId,
						target_node_id: pendingRelation.targetId,
						label,
						description: relationDescription,
						confidence
					})
				: await narrativeApi.createRelation(params.graphId, params.chapterId, pendingRelation.sourceId, pendingRelation.targetId, {
						relationType,
						label,
						description: relationDescription,
						confidence
					});
			message = `Relation ${(await waitForBatch(batch.id)).status}.`;
			relationDialogOpen = false;
			pendingRelation = null;
			await load();
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not create relation.';
		} finally {
			creatingRelation = false;
		}
	}
	async function deleteRelation() {
		if (!editingRelationId) return;
		deletingRelation = true;
		try {
			const batch = await narrativeApi.deleteRelation(params.graphId, editingRelationId);
			await waitForBatch(batch.id);
			deleteRelationDialogOpen = false;
			relationDialogOpen = false;
			editingRelationId = null;
			await load();
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not remove relation.';
		} finally {
			deletingRelation = false;
		}
	}
	async function waitForBatch(batchId: string) {
		for (let attempt = 0; attempt < 60; attempt += 1) {
			await new Promise((resolve) => setTimeout(resolve, 500));
			const batch = await narrativeApi.getBatch(params.graphId, batchId);
			if (!['accepted', 'applying'].includes(batch.status)) return batch;
		}
		throw new Error('The graph update is taking longer than expected. Please try again shortly.');
	}
</script>

<main class="relative grid h-screen min-h-0 grid-cols-[3.5rem_minmax(0,1fr)_minmax(0,1fr)] bg-background">
	<aside class="flex flex-col items-center gap-3 border-r py-4">
		<StoryMenu graphId={params.graphId} compact />
		<ToolToggle
			label="Extract graph proposals from chapter text"
			toggleable={false}
			disabled={Boolean(agentRunning)}
			onclick={() => void runAgent('analysis')}
			>{#if agentRunning === 'analysis'}<Loader2 class="size-5 animate-spin text-primary" />{:else}<BrainCircuit class="size-5 text-blue-500" />{/if}</ToolToggle
		>
		<ToolToggle
			label="Suggest prose from the chapter graph"
			toggleable={false}
			disabled={Boolean(agentRunning)}
			onclick={() => void runAgent('draft')}>{#if agentRunning === 'draft'}<Loader2 class="size-5 animate-spin text-primary" />{:else}<PenTool class="size-5 text-green-500" />{/if}</ToolToggle
		>
		<ToolToggle
			label="Check continuity and graph feedback"
			toggleable={false}
			disabled={Boolean(agentRunning)}
			onclick={() => void runAgent('review')}>{#if agentRunning === 'review'}<Loader2 class="size-5 animate-spin text-primary" />{:else}<ClipboardCheck class="size-5 text-purple-500" />{/if}</ToolToggle
		>
		<ToolToggle
			label="Check this chapter's history, technology, customs, places, and lore for possible inconsistencies"
			toggleable={false}
			disabled={Boolean(agentRunning)}
			onclick={() => void runAgent('research')}
			>{#if agentRunning === 'research'}<Loader2 class="size-5 animate-spin text-primary" />{:else}<Search class="size-5 text-amber-500" />{/if}</ToolToggle
		>
		<ToolToggle
			label="Generate a storyboard image"
			toggleable={false}
			disabled={Boolean(agentRunning)}
			onclick={() => void runAgent('visuals')}>{#if agentRunning === 'visuals'}<Loader2 class="size-5 animate-spin text-primary" />{:else}<ImageIcon class="size-5 text-pink-500" />{/if}</ToolToggle
		>
		<ToolToggle
			label="Generate dialogue audio"
			toggleable={false}
			disabled={Boolean(agentRunning)}
			onclick={() => void runAgent('voice')}>{#if agentRunning === 'voice'}<Loader2 class="size-5 animate-spin text-primary" />{:else}<Mic class="size-5 text-cyan-500" />{/if}</ToolToggle
		>
		<ToolToggle
			label="Run chapter production"
			toggleable={false}
			disabled={Boolean(agentRunning)}
			onclick={() => void runAgent('produce')}>{#if agentRunning === 'produce'}<Loader2 class="size-5 animate-spin text-primary" />{:else}<Film class="size-5 text-rose-500" />{/if}</ToolToggle
		>
		<div class="mt-auto pt-4">
			<Dialog.Root>
				<Dialog.Trigger>
					<Button size="icon" variant="ghost" title="How to Use" aria-label="How to Use">
						<CircleHelp class="size-5 text-muted-foreground" />
					</Button>
				</Dialog.Trigger>
				<Dialog.Content>
					<Dialog.Header>
						<Dialog.Title>How to Use</Dialog.Title>
						<Dialog.Description>
							Quick guide on formatting for the text editor.
						</Dialog.Description>
					</Dialog.Header>
					<div class="space-y-4">
						<div>
							<h4 class="font-medium text-sm">Dialogue Format</h4>
							<p class="text-sm text-muted-foreground mt-1">
								For dialogue tones, you can specify them using brackets:<br />
								<code class="bg-muted px-1 py-0.5 rounded">[character] (emotion and genre) : "dialogue"</code>
							</p>
						</div>
					</div>
				</Dialog.Content>
			</Dialog.Root>
		</div>
	</aside>
	<section class="flex min-h-0 flex-col border-r">
		<header class="flex items-center justify-between border-b px-5 py-3">
			<div>
				<nav class="text-xs text-muted-foreground">
					<button
						class="transition-colors hover:text-foreground hover:underline focus-visible:text-foreground focus-visible:underline"
						onclick={() => goto(resolve(`/stories/${params.graphId}`))}>Story</button
					>
					/
					{#if selection}<button
							class="transition-colors hover:text-foreground hover:underline focus-visible:text-foreground focus-visible:underline"
							onclick={() => void clearNodeSelection()}>{chapter?.title ?? 'Chapter'}</button
						>{:else}<span>{chapter?.title ?? 'Chapter'}</span>{/if}{#if selection}
						/ <span>{selectedLabel || 'Selected element'}</span>{/if}
				</nav>
				{#if editingChapterTitle}<form
						class="mt-1 flex max-w-md gap-2"
						onsubmit={(event) => {
							event.preventDefault();
							void saveChapterTitle();
						}}
					>
						<Input bind:value={chapterTitleDraft} aria-label="Chapter title" autofocus />
						<Button
							size="sm"
							type="submit"
							disabled={savingChapterTitle || !chapterTitleDraft.trim()}
							>{savingChapterTitle ? 'Saving…' : 'Save'}</Button
						>
						<Button
							size="sm"
							variant="outline"
							type="button"
							disabled={savingChapterTitle}
							onclick={() => (editingChapterTitle = false)}>Cancel</Button
						>
					</form>{:else}<div class="flex items-center gap-2">
						<h1 class="text-lg font-semibold">{chapter?.title ?? 'Loading…'}</h1>
						<Button size="sm" variant="ghost" onclick={startEditingChapterTitle}>Edit</Button>
					</div>{/if}
			</div>
			<Badge
				variant={saveState === 'error'
					? 'destructive'
					: saveState === 'saving'
						? 'secondary'
						: 'outline'}>{saveState}</Badge
			>
		</header>
		<div class="relative flex gap-2 border-b px-4 py-2">
			<label class="sr-only" for="chapter-picker">Choose a chapter</label>
			<Input
				id="chapter-picker"
				class="h-8 flex-1"
				bind:value={chapterQuery}
				placeholder="Search chapters…"
				role="combobox"
				aria-autocomplete="list"
				aria-expanded={chapterPickerOpen}
				onfocus={() => (chapterPickerOpen = true)}
				oninput={() => (chapterPickerOpen = true)}
			/>
			{#if previousChapter}<Button
				size="sm"
				variant="outline"
				onclick={() => selectChapter(previousChapter)}>Previous</Button
			>{/if}
			{#if nextChapter}<Button
				size="sm"
				variant="outline"
				onclick={() => selectChapter(nextChapter)}>Next</Button
			>{/if}
			<Button
				size="sm"
				variant="destructive"
				disabled={chapters.length <= 1}
				title={chapters.length <= 1 ? 'A story needs at least one chapter.' : 'Delete chapter'}
				onclick={() => (deleteDialogOpen = true)}>Delete</Button
			>
			{#if chapterPickerOpen}<div
					class="absolute top-full right-4 left-4 z-20 mt-1 max-h-48 overflow-y-auto rounded-md border bg-popover p-1 shadow-md"
					role="listbox"
				>
					{#each matchingChapters as storyChapter (storyChapter.id)}<button
							class="block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
							class:bg-accent={storyChapter.id === params.chapterId}
							role="option"
							aria-selected={storyChapter.id === params.chapterId}
							onmousedown={(event) => event.preventDefault()}
							onclick={() => selectChapter(storyChapter)}
							>{storyChapter.sequence}. {storyChapter.title}</button
						>{:else}<p class="px-2 py-1.5 text-sm text-muted-foreground">
							No chapters found.
						</p>{/each}
				</div>{/if}
		</div>
		{#if selectedRecord}<aside
				class="flex min-h-0 flex-1 flex-col overflow-y-auto bg-muted/30 px-5 py-5"
			>
				<div class="flex items-center justify-between">
					<p class="text-xs font-semibold tracking-wide text-primary uppercase">
						Selected graph element
					</p>
					<div class="flex gap-2">
						<Button size="sm" variant="destructive" onclick={() => (deleteNodeDialogOpen = true)}
							>Delete</Button
						>
					</div>
				</div>
				<h2 class="mt-3 text-xl font-semibold">{selectedLabel}</h2>
				<p class="mt-1 text-sm text-muted-foreground">
					Included in {chapter?.title ?? 'this chapter'}.
				</p>
				<div class="mt-5 grid gap-4">
					<label
							class="grid gap-1 text-sm">Name<Input bind:value={nodeFormName} /></label
						>
					{#if selectedNodeKind === 'knowledge_element'}<label class="grid gap-1 text-sm"
							>Element type<select
								class="h-8 rounded border bg-background px-2"
								bind:value={nodeFormType}
								><option value="assumption">Assumption</option><option value="attribute"
									>Attribute</option
								><option value="constraint">Constraint</option><option value="fact">Fact</option
								><option value="note">Note</option><option value="statement">Statement</option
								></select
							></label
						>{:else if selectedNodeKind === 'entity'}<label class="grid gap-1 text-sm"
							>Entity type<select
								class="h-8 rounded border bg-background px-2"
								bind:value={nodeFormType}
								>{#if nodeFormType && !entityTypeOptions.some((option) => option.value === nodeFormType)}<option
										value={nodeFormType}>{nodeFormType}</option
									>{/if}{#each entityTypeOptions as option}<option value={option.value}
										>{option.label}</option
									>{/each}</select
							></label
						>{:else if selectedNodeKind === 'event'}<label class="grid gap-1 text-sm">Event type<select class="h-8 rounded border bg-background px-2" bind:value={nodeFormType}
							>{#if nodeFormType && !eventTypeOptions.some((option) => option.value === nodeFormType)}<option value={nodeFormType}>{nodeFormType}</option>{/if}{#each eventTypeOptions as option}<option value={option.value}>{option.label}</option>{/each}</select
							></label
						>{:else}<label class="grid gap-1 text-sm">Context type<select class="h-8 rounded border bg-background px-2" bind:value={nodeFormType}
							>{#if nodeFormType && !contextTypeOptions.some((option) => option.value === nodeFormType)}<option value={nodeFormType}>{nodeFormType}</option>{/if}{#each contextTypeOptions as option}<option value={option.value}>{option.label}</option>{/each}</select
							></label
						>{/if}
					{#if selectedNodeKind !== 'context'}<label class="grid gap-1 text-sm"
							>Status<select
								class="h-8 rounded border bg-background px-2"
								bind:value={nodeFormStatus}
								><option value="active">Active</option><option value="draft">Draft</option><option
									value="inactive">Inactive</option
								></select
							></label
						>{/if}
					{#if selectedNodeKind === 'entity'}<label class="grid gap-1 text-sm"
							>Aliases <span class="text-xs text-muted-foreground">(comma separated)</span><Input
								bind:value={nodeFormAliases}
							/></label
						>{/if}
					{#if selectedNodeKind === 'entity' || selectedNodeKind === 'event' || selectedNodeKind === 'context' || selectedNodeKind === 'knowledge_element'}<label
							class="grid gap-1 text-sm">Content<Textarea bind:value={nodeFormContent} /></label
						><label
							class="grid gap-1 text-sm"
							>Description<Textarea bind:value={nodeFormDescription} /></label
						>{/if}
					{#if selectedNodeKind === 'context'}<label class="grid gap-1 text-sm"
							>Holder entity ID<Input bind:value={nodeFormHolder} /></label
						>{/if}
					{#if selectedNodeKind === 'knowledge_element'}<label class="grid gap-1 text-sm"
							>Origin<Input bind:value={nodeFormOrigin} /></label
						>{/if}
					<label class="grid gap-1 text-sm"
						>Confidence<Input
							type="number"
							min="0"
							max="1"
							step="0.01"
							bind:value={nodeFormConfidence}
						/></label
					>
					<Button class="mt-2" disabled={savingNode} onclick={() => void saveNodeEdits()}
						>{savingNode ? 'Saving…' : 'Save changes'}</Button
					>
				</div>
				{#if selectedRelations.length}<section class="mt-5 border-t pt-4">
						<p class="text-xs font-semibold tracking-wide text-primary uppercase">Connections</p>
						<div class="mt-2 grid gap-2">
							{#each selectedRelations as relation (relation.id)}<button
									class="rounded-md border bg-background p-3 text-left transition-colors hover:bg-muted"
									disabled={!relation.otherRecord || !relation.otherKind}
									onclick={() => {
										if (relation.otherRecord && relation.otherKind) {
											selectNode(
												relation.otherId,
												relation.otherLabel,
												relation.otherKind,
												relation.otherRecord
											);
										}
									}}
								>
									<p class="text-sm font-medium">
										{relation.outgoing ? '→' : '←'}
										{relation.label} · {relation.otherLabel}
									</p>
									<p class="mt-1 text-xs text-muted-foreground">
										{relation.relationType}{relation.description
											? ` · ${relation.description}`
											: ''}
									</p>
								</button>{/each}
						</div>
					</section>{/if}
				{#if selectedRecord.metadata}<div class="mt-5 border-t pt-4">
						<p class="text-xs font-semibold tracking-wide text-primary uppercase">
							Additional details
						</p>
						<dl class="mt-2 grid gap-2 text-sm text-muted-foreground">
							{#each Object.entries(selectedRecord.metadata as Record<string, unknown>).filter(([key]) => key !== 'chapter_id') as [key, value] (key)}<div
								>
									<dt class="font-medium text-foreground">{key.replaceAll('_', ' ')}</dt>
									<dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>
								</div>{/each}
						</dl>
					</div>{/if}
			</aside>{/if}
		{#if textProposals.length}<aside class="border-b bg-muted/30 px-5 py-3">
				<div class="mb-2 flex items-center justify-between">
					<p class="text-xs font-semibold tracking-wide text-primary uppercase">Text proposals</p>
					<Button size="sm" variant="ghost" onclick={() => (textProposals = [])}>Dismiss all</Button
					>
				</div>
				{#each textProposals as proposal (proposal.id)}<div
						class="mb-2 rounded-md border bg-background p-2"
					>
						<p class="text-sm">{proposal.text}</p>
						<p class="mt-1 text-xs text-muted-foreground">{proposal.rationale}</p>
						<div class="mt-2 flex gap-2">
							<Button size="sm" onclick={() => void applyTextProposal(proposal)}
								>Accept into chapter</Button
							>
							<Button
								size="sm"
								variant="ghost"
								onclick={() =>
									(textProposals = textProposals.filter((item) => item.id !== proposal.id))}
								>Dismiss</Button
							>
						</div>
					</div>{/each}
			</aside>{/if}
		{#if agentOutput}<aside class="max-h-64 overflow-y-auto border-b bg-primary/5 px-5 py-3">
				<div class="flex items-center justify-between gap-3">
					<div>
						<p class="text-xs font-semibold tracking-wide text-primary uppercase">
							AI {agentOutput.agent_group}
						</p>
						<p class="text-sm text-muted-foreground">{agentOutput.message}</p>
					</div>
					<div class="flex items-center gap-2">
						<Badge variant={agentOutput.status === 'failed' ? 'destructive' : 'outline'}
							>{agentOutput.status}</Badge
						>
						<Button size="sm" variant="ghost" onclick={dismissAgentResults}>Close results</Button>
					</div>
				</div>
				{#if agentOutput.result.stages?.length}<p class="mt-2 text-xs text-muted-foreground">
						Stages: {agentOutput.result.stages
							.map((stage) => stage.replaceAll('_', ' '))
							.join(' · ')}
					</p>{/if}
				{#if agentOutput.result.findings?.length}<div class="mt-3 grid gap-2">
						{#each agentOutput.result.findings as finding}<article
								class="rounded border bg-background p-2 text-sm"
							>
								<p class="font-medium">{finding.severity}: {finding.message}</p>
								{#if finding.suggestion}<p class="mt-1 text-muted-foreground">
										{finding.suggestion}
									</p>{/if}
							</article>{/each}
					</div>{/if}
				{#if agentOutput.result.report}<details
						class="mt-3 rounded border bg-background p-2 text-sm"
					>
						<summary class="cursor-pointer font-medium">Research report</summary>
						<pre class="mt-2 overflow-x-auto text-xs whitespace-pre-wrap">{JSON.stringify(
								agentOutput.result.report,
								null,
								2
							)}</pre>
					</details>{/if}
				{#if storedStoryboardScenes.length}<section class="mt-3 grid gap-3 sm:grid-cols-2">
						{#each storedStoryboardScenes as scene (scene.scene_id)}<article class="overflow-hidden rounded border bg-background">
								{#if scene.image_url}<img
										class="aspect-video w-full object-cover"
										src={mediaUrl(scene.image_url)}
										alt={`Storyboard for ${scene.title}`}
									/>{/if}
								<div class="p-2">
									<p class="font-medium">{scene.title}</p>
									<p class="text-xs text-muted-foreground">{scene.header}</p>
									<p class="mt-1 text-xs text-muted-foreground">{scene.excerpt}</p>
								</div>
							</article>{/each}
					</section>{:else if agentOutput.result.media?.image_url}<img
						class="mt-3 max-h-48 rounded border object-cover"
						src={mediaUrl(agentOutput.result.media.image_url)}
						alt="Generated storyboard for this chapter"
					/>{/if}
				{#if agentOutput.result.media?.dialogues?.length || agentOutput.result.dialogues?.dialogues?.length}<div
						class="mt-3 grid gap-2"
					>
						{#each agentOutput.result.media?.dialogues ?? agentOutput.result.dialogues?.dialogues ?? [] as dialogue, index (index)}<article
								class="rounded border bg-background p-2 text-sm"
							>
								<p class="font-medium">{dialogue.speaker}</p>
								<p class="text-muted-foreground">{dialogue.line}</p>
								{#if dialogue.audio_url}<audio class="mt-2 w-full" controls src={mediaUrl(dialogue.audio_url)}
									><track kind="captions" /></audio
								>{/if}
							</article>{/each}
					</div>{/if}
				{#if agentOutput.result.text_patches?.length}<Button
						class="mt-3"
						size="sm"
						onclick={() => void acceptAgentPatches()}>Accept all reviewed text</Button
					>{/if}
			</aside>{/if}
		{#if !selectedRecord && chapter}<div class="min-h-0 flex-1 p-4">
				<ChapterEditor
					document={chapter.document}
					highlight={selectedLabel}
					onchange={scheduleSave}
				/>
			</div>{/if}
	</section>
	<section class="relative flex min-h-0 flex-col">
		<header class="flex items-center justify-between border-b px-5 py-3">
			<div>
				<p class="text-xs text-muted-foreground">
					<button
						class="transition-colors hover:text-foreground hover:underline focus-visible:text-foreground focus-visible:underline"
						onclick={() => goto(resolve(`/stories/${params.graphId}`))}>Story</button
					>
					/
					{#if selection}<button
							class="transition-colors hover:text-foreground hover:underline focus-visible:text-foreground focus-visible:underline"
							onclick={() => void clearNodeSelection()}>{chapter?.title ?? 'Chapter'}</button
						>{:else}<span>{chapter?.title ?? 'Chapter'}</span>{/if}{#if selection}
						/ {selectedLabel || 'Node'}{/if}
				</p>
				<h2 class="text-lg font-semibold">Narrative graph</h2>
			</div>
			<div class="flex items-center gap-2">
				<Button size="sm" variant="outline" onclick={openChapterTimeline}>Chapter timeline</Button
				><Button
					size="sm"
					variant="outline"
					disabled={proposingText}
					onclick={() => void proposeTextFromGraph()}
					>{proposingText ? 'Reviewing…' : 'Suggest prose'}</Button
				>
				<Button size="sm" onclick={() => void openNodeSidebar()}>New node</Button>
			</div>
		</header>
		<div class="min-h-0 flex-1 p-4">
			<NarrativeCanvas {subgraph} onselect={selectNode} onconnect={beginRelation} oneditrelation={editRelation} />
		</div>
		{#if nodeSidebarOpen}<NodeCreateSidebar
				creating={creatingNode}
				{existingNodes}
				onclose={() => (nodeSidebarOpen = false)}
				oncreate={(kind, values) => void createNode(kind, values)}
				onlink={(id, nodeType) => void linkExistingNode(id, nodeType)}
			/>{/if}
		{#if proposals.length}<aside class="relative max-h-56 overflow-y-auto border-t bg-card p-4">
				<div class="mb-2 flex items-center justify-between">
					<strong>{proposalSource === 'review' ? 'Continuity graph suggestions' : 'Extracted graph proposals'}</strong><Button
							size="sm"
							variant="ghost"
							disabled={applyingProposals}
							onclick={dismissGraphProposals}>Dismiss all</Button
					><Button
							size="sm"
							disabled={applyingProposals || !selectedProposalIds.length}
							aria-busy={applyingProposals}
							onclick={() => void apply()}
							>{#if applyingProposals}<span class="animate-spin">◌</span> Adding to graph…{:else}Apply selected{/if}</Button
					>
				</div>
				{#each proposals as proposal (proposal.id)}<label class="flex gap-2 py-2 text-sm"
						><input
							type="checkbox"
							checked={selectedProposalIds.includes(proposal.id)}
							disabled={applyingProposals}
							onchange={() =>
								(selectedProposalIds = selectedProposalIds.includes(proposal.id)
									? selectedProposalIds.filter((id) => id !== proposal.id)
									: [...selectedProposalIds, proposal.id])}
						/><span
							><span class="font-medium">{proposalSummary(proposal)}</span
							>{#if proposalExcerpt(proposal)}<span
									class="mt-0.5 block text-xs text-muted-foreground"
									>From: {proposalExcerpt(proposal)}</span
								>{/if}</span
						></label
					>{/each}
				{#if applyingProposals}<div class="absolute inset-0 grid place-items-center bg-card/75 backdrop-blur-[1px]">
						<p class="rounded-md border bg-background px-3 py-2 text-sm font-medium shadow-sm">Adding selected nodes and relations to the graph…</p>
					</div>{/if}
			</aside>{/if}
	</section>
	{#if loading}
		<div class="absolute inset-0 z-30 grid place-items-center bg-background/70 backdrop-blur-sm">
			<p class="rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">Loading chapter…</p>
		</div>
	{/if}
</main>
<Dialog.Root bind:open={storyboardReviewOpen}>
	<Dialog.Content class="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
		<Dialog.Header>
			<Dialog.Title>Choose storyboard images to keep</Dialog.Title>
			<Dialog.Description>
				Review each generated scene. Only images marked “Store” will be saved to this chapter.
			</Dialog.Description>
		</Dialog.Header>
		{#if currentStoryboardScene}<div class="grid gap-4">
				<div class="overflow-hidden rounded-lg border bg-muted/30">
					{#if currentStoryboardScene.image_url}<img
							class="aspect-video w-full object-cover"
							src={mediaUrl(currentStoryboardScene.image_url)}
							alt={`Storyboard for ${currentStoryboardScene.title}`}
						/>{/if}
					<div class="p-4">
						<p class="text-lg font-semibold">{currentStoryboardScene.title}</p>
						<p class="text-sm text-muted-foreground">{currentStoryboardScene.header}</p>
						<p class="mt-2 text-sm">{currentStoryboardScene.excerpt}</p>
					</div>
				</div>
				<div class="flex items-center justify-between gap-3">
					<Button
						variant="outline"
						disabled={storyboardIndex === 0}
						onclick={() => (storyboardIndex -= 1)}>Previous</Button
					>
					<p class="text-sm text-muted-foreground">
						Scene {storyboardIndex + 1} of {generatedStoryboardScenes.length}
					</p>
					<Button
						variant="outline"
						disabled={storyboardIndex >= generatedStoryboardScenes.length - 1}
						onclick={() => (storyboardIndex += 1)}>Next</Button
					>
				</div>
				<Toggle
					label="Store this image"
					description="Turn this off to discard the current scene."
					checked={selectedStoryboardIds.includes(currentStoryboardScene.scene_id)}
					oncheckedchange={() => toggleStoryboardSelection(currentStoryboardScene.scene_id)}
				/>
			</div>{/if}
		<Dialog.Footer>
			<Button variant="outline" disabled={savingStoryboards} onclick={() => void discardStoryboards()}>Discard all</Button>
			<Button
				disabled={savingStoryboards || !selectedStoryboardIds.length}
				onclick={() => void storeSelectedStoryboards()}
				>{savingStoryboards
					? 'Saving…'
					: `Store selected (${selectedStoryboardIds.length})`}</Button
			>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
<Dialog.Root bind:open={agentResultsOpen}>
	<Dialog.Content class="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
		<Dialog.Header>
			<Dialog.Title>{agentOutput?.agent_group === 'review' ? 'Continuity and graph feedback' : 'Historical accuracy and lore research'}</Dialog.Title>
			<Dialog.Description>{agentOutput?.message ?? 'The agent result is ready to review.'}</Dialog.Description>
		</Dialog.Header>
		{#if agentOutput?.agent_group === 'review'}<div class="grid gap-3">
				{#each agentOutput.result.findings ?? [] as finding}<article class="rounded-md border p-3">
					<p class="text-xs font-semibold uppercase text-primary">{finding.severity}</p>
					<p class="mt-1 font-medium">{finding.message}</p>
					{#if finding.suggestion}<p class="mt-1 text-sm text-muted-foreground">{finding.suggestion}</p>{/if}
				</article>{/each}
				{#if agentOutput.result.graph_proposals?.length && proposalSource === 'review'}<p class="rounded-md bg-muted p-3 text-sm">
					{agentOutput.result.graph_proposals.length} graph feedback proposal(s) are available in the graph panel. Select the facts you want, then use <strong>Apply selected</strong>.
				</p>{/if}
			</div>{:else if agentOutput?.result.report}<div class="grid gap-3">
				<section class="rounded-md border bg-muted/30 p-3 text-sm">
					<h3 class="font-semibold">What this research checked</h3>
					<p class="mt-1 text-muted-foreground">
						It reviewed <strong>{String(researchScope.material ?? 'the current chapter text')}</strong>
						for historical era, technology, places, customs, and internal story lore.
					</p>
					{#if agentOutput.result.report.query}<p class="mt-2 text-xs text-muted-foreground">
						Analyzed excerpt: “{String(agentOutput.result.report.query).slice(0, 280)}{String(agentOutput.result.report.query).length > 280 ? '…' : ''}”
					</p>{/if}
				</section>
				<div class="rounded-md border p-3">
					<p class="text-xs font-semibold uppercase text-primary">{agentOutput.result.report.verdict ?? 'Research result'}</p>
					<p class="mt-1 text-sm">{agentOutput.result.report.historical_summary ?? 'No summary was returned.'}</p>
					{#if agentOutput.result.report.era_analyzed}<p class="mt-2 text-xs text-muted-foreground">Era: {agentOutput.result.report.era_analyzed} · Confidence: {Math.round((agentOutput.result.report.confidence_score ?? 0) * 100)}%</p>{/if}
				</div>
				<section class="rounded-md border p-3 text-sm">
					<h3 class="font-semibold">How to read confidence</h3>
					<p class="mt-1 text-muted-foreground">
						Confidence estimates how strongly the result is supported by the chapter details and available reference material. It is guidance for revision, not proof that a creative choice is wrong.
					</p>
					<p class="mt-2 text-xs text-muted-foreground">
						Evidence coverage: {agentOutput.result.report.search_sources?.length ? `${agentOutput.result.report.search_sources.length} external source(s) were consulted.` : 'No external sources were available; this is a local consistency audit.'}
					</p>
				</section>
				{#if agentOutput.result.report.detected_anachronisms?.length}<section>
					<h3 class="text-sm font-semibold">Potential anachronisms</h3>
					{#each agentOutput.result.report.detected_anachronisms as issue}<article class="mt-2 rounded-md border border-destructive/30 p-3 text-sm">
						<p class="font-medium">{issue.element ?? 'Potential issue'}</p>
						<p class="mt-1 text-muted-foreground">{issue.issue}</p>
						{#if issue.periodAccurateAlternative}<p class="mt-1">Alternative: {issue.periodAccurateAlternative}</p>{/if}
					</article>{/each}
				</section>{/if}
				{#if agentOutput.result.report.recommendations_for_writers}<section class="rounded-md bg-muted p-3 text-sm"><h3 class="font-semibold">Recommendations</h3><p class="mt-1">{agentOutput.result.report.recommendations_for_writers}</p></section>{/if}
				{#if agentOutput.result.report.search_sources?.length}<section><h3 class="text-sm font-semibold">Sources</h3>{#each agentOutput.result.report.search_sources as source}<a class="mt-2 block rounded-md border p-3 text-sm hover:bg-muted" href={source.url} target="_blank" rel="noreferrer"><p class="font-medium">{source.title ?? source.url}</p>{#if source.excerpts?.length}<p class="mt-1 text-muted-foreground">{source.excerpts[0]}</p>{/if}</a>{/each}</section>{/if}
			</div>{/if}
		<Dialog.Footer>
			{#if agentOutput?.agent_group === 'review' && proposalSource === 'review'}<Button
					variant="outline"
					disabled={applyingProposals}
					onclick={() => {
						dismissGraphProposals();
						agentResultsOpen = false;
					}}>Dismiss suggestions</Button
			>{/if}
			<Button onclick={() => (agentResultsOpen = false)}>Done</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={deleteDialogOpen}>
	<Dialog.Content>
		<Dialog.Header>
			<Dialog.Title>Delete chapter?</Dialog.Title>
			<Dialog.Description>
				This permanently removes “{chapter?.title ?? 'this chapter'}” and its written text. This
				cannot be undone.
			</Dialog.Description>
		</Dialog.Header>
		<Dialog.Footer>
			<Button
				variant="outline"
				disabled={deletingChapter}
				onclick={() => (deleteDialogOpen = false)}>Cancel</Button
			>
			<Button
				variant="destructive"
				disabled={deletingChapter}
				onclick={() => void deleteCurrentChapter()}
				>{deletingChapter ? 'Deleting…' : 'Delete chapter'}</Button
			>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
<Dialog.Root bind:open={editNodeDialogOpen}>
	<Dialog.Content class="max-h-[90vh] overflow-y-auto sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>Edit {selectedLabel}</Dialog.Title>
			<Dialog.Description
				>Update this graph element. Changes are recorded in the graph journal.</Dialog.Description
			>
		</Dialog.Header>
		<div class="grid gap-3">
			{#if selectedNodeKind === 'entity' || selectedNodeKind === 'event'}<label
					class="grid gap-1 text-sm">Name<Input bind:value={nodeFormName} /></label
				>{/if}
			{#if selectedNodeKind === 'knowledge_element'}<label class="grid gap-1 text-sm"
					>Element type<select
						class="h-8 rounded border bg-background px-2"
						bind:value={nodeFormType}
						><option value="assumption">Assumption</option><option value="attribute"
							>Attribute</option
						><option value="constraint">Constraint</option><option value="fact">Fact</option><option
							value="note">Note</option
						><option value="statement">Statement</option></select
					></label
				>{:else if selectedNodeKind === 'entity'}<label class="grid gap-1 text-sm"
					>Entity type<select
						class="h-8 rounded border bg-background px-2"
						bind:value={nodeFormType}
						>{#if nodeFormType && !entityTypeOptions.some((option) => option.value === nodeFormType)}<option
								value={nodeFormType}>{nodeFormType}</option
							>{/if}{#each entityTypeOptions as option}<option value={option.value}
								>{option.label}</option
							>{/each}</select
					></label
				>{:else if selectedNodeKind === 'event'}<label class="grid gap-1 text-sm">Event type<select class="h-8 rounded border bg-background px-2" bind:value={nodeFormType}
					>{#if nodeFormType && !eventTypeOptions.some((option) => option.value === nodeFormType)}<option value={nodeFormType}>{nodeFormType}</option>{/if}{#each eventTypeOptions as option}<option value={option.value}>{option.label}</option>{/each}</select
					></label
				>{:else}<label class="grid gap-1 text-sm">Context type<select class="h-8 rounded border bg-background px-2" bind:value={nodeFormType}
					>{#if nodeFormType && !contextTypeOptions.some((option) => option.value === nodeFormType)}<option value={nodeFormType}>{nodeFormType}</option>{/if}{#each contextTypeOptions as option}<option value={option.value}>{option.label}</option>{/each}</select
					></label
				>{/if}
			{#if selectedNodeKind !== 'context'}<label class="grid gap-1 text-sm"
					>Status<select class="h-8 rounded border bg-background px-2" bind:value={nodeFormStatus}
						><option value="active">Active</option><option value="inactive">Inactive</option><option
							value="draft">Draft</option
						><option value="invalidated">Invalidated</option></select
					></label
				>{/if}
			{#if selectedNodeKind === 'entity'}<label class="grid gap-1 text-sm"
					>Aliases <span class="text-xs text-muted-foreground">(comma separated)</span><Input
						bind:value={nodeFormAliases}
						placeholder="e.g. The Captain, A. Rivera"
					/></label
				>{/if}
			{#if selectedNodeKind === 'event'}<label class="grid gap-1 text-sm"
					>Description<Textarea bind:value={nodeFormDescription} /></label
				>{/if}
			{#if selectedNodeKind === 'context'}<label class="grid gap-1 text-sm"
					>Holder entity ID <span class="text-xs text-muted-foreground">(optional)</span><Input
						bind:value={nodeFormHolder}
						placeholder="Entity UUID"
					/></label
				>{/if}
			{#if selectedNodeKind === 'knowledge_element'}<label class="grid gap-1 text-sm"
					>Origin<Input bind:value={nodeFormOrigin} /></label
				>{/if}
			<label class="grid gap-1 text-sm"
				>Confidence <span class="text-xs text-muted-foreground">(0 to 1)</span><Input
					type="number"
					min="0"
					max="1"
					step="0.01"
					bind:value={nodeFormConfidence}
				/></label
			>
			<div class="grid gap-2">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-medium">Additional details</p>
						<p class="text-xs text-muted-foreground">
							Optional information that helps describe this node.
						</p>
					</div>
					<Button
						size="sm"
						variant="outline"
						onclick={() => (metadataEntries = [...metadataEntries, { key: '', value: '' }])}
						>Add detail</Button
					>
				</div>
				{#each metadataEntries as entry, index (index)}<div class="flex gap-2">
						<Input bind:value={entry.key} placeholder="Detail, e.g. role" />
						<Input bind:value={entry.value} placeholder="Value, e.g. protagonist" />
						<Button
							size="sm"
							variant="ghost"
							disabled={metadataEntries.length === 1}
							onclick={() =>
								(metadataEntries = metadataEntries.filter((_, itemIndex) => itemIndex !== index))}
							>Remove</Button
						>
					</div>{/each}
			</div>
		</div>
		<Dialog.Footer>
			<Button variant="outline" disabled={savingNode} onclick={() => (editNodeDialogOpen = false)}
				>Cancel</Button
			>
			<Button disabled={savingNode} onclick={() => void saveNodeEdits()}
				>{savingNode ? 'Saving…' : 'Save changes'}</Button
			>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
<Dialog.Root bind:open={deleteNodeDialogOpen}>
	<Dialog.Content>
		<Dialog.Header>
			<Dialog.Title>Remove graph element?</Dialog.Title>
			<Dialog.Description>
				This removes “{selectedLabel}” from the active graph. Its operation history is retained for
				provenance, but the element will no longer appear in the story workspace.
			</Dialog.Description>
		</Dialog.Header>
		<Dialog.Footer>
			<Button
				variant="outline"
				disabled={deletingNode}
				onclick={() => (deleteNodeDialogOpen = false)}>Cancel</Button
			>
			<Button
				variant="destructive"
				disabled={deletingNode}
				onclick={() => void deleteSelectedNode()}
				>{deletingNode ? 'Removing…' : 'Remove element'}</Button
			>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
<Dialog.Root bind:open={relationDialogOpen}>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>{editingRelationId ? 'Edit connection' : 'Describe this connection'}</Dialog.Title>
			<Dialog.Description>
				{pendingRelation?.sourceLabel ?? 'Source'} â†’ {pendingRelation?.targetLabel ?? 'Target'}
			</Dialog.Description>
		</Dialog.Header>
		<div class="grid gap-4">
			{#if editingRelationId}<div class="grid gap-3 sm:grid-cols-2">
					<label class="grid gap-1 text-sm font-medium">From<select
							class="h-9 rounded-md border bg-background px-2"
							value={pendingRelation?.sourceId ?? ''}
							onchange={(event) => setRelationEndpoint('source', event.currentTarget.value)}
						>{#each relationNodes() as node (node.id)}<option value={node.id}>{node.label}</option>{/each}</select
						></label
					>
					<label class="grid gap-1 text-sm font-medium">To<select
							class="h-9 rounded-md border bg-background px-2"
							value={pendingRelation?.targetId ?? ''}
							onchange={(event) => setRelationEndpoint('target', event.currentTarget.value)}
						>{#each relationNodes() as node (node.id)}<option value={node.id}>{node.label}</option>{/each}</select
						></label
					>
				</div>{/if}
			<label class="grid gap-1 text-sm font-medium"
				>Relation kind<select
					class="h-9 rounded-md border bg-background px-2"
					value={relationType}
					disabled={Boolean(editingRelationId)}
					onchange={(event) =>
						changeRelationType(event.currentTarget.value as 'statement' | 'context')}
					><option value="statement">Statement</option><option value="context">Context</option
					></select
				></label
			>
			{#if relationType === 'statement'}<p class="text-sm text-muted-foreground">
					A statement records a claim between these two nodes and becomes a knowledge element.
				</p>{:else}<p class="text-sm text-muted-foreground">
					A context relation connects a node to a context without creating a statement.
				</p>{/if}
			<label class="grid gap-1 text-sm font-medium"
				>{relationType === 'statement' ? 'Relation predicate' : 'Context role'}
				<span class="text-destructive">*</span><select
					class="h-9 rounded-md border bg-background px-2"
					bind:value={relationLabel}
					>{#if relationType === 'statement'}<option value="related_to">Related to</option><option
							value="knows">Knows</option
						><option value="trusts">Trusts</option><option value="supports">Supports</option><option
							value="opposes">Opposes</option
						><option value="owns">Owns</option><option value="seeks">Seeks</option><option
							value="located_in">Located in</option
						><option value="participates_in">Participates in</option><option value="causes"
							>Causes</option
						><option value="precedes">Precedes</option>{:else}<option value="takes_place_in"
							>Takes place in</option
						><option value="applies_in">Applies in</option><option value="viewed_through"
							>Viewed through</option
						><option value="governed_by">Governed by</option>{/if}<option value="custom"
						>Customâ€¦</option
					></select
				></label
			>
			{#if relationLabel === 'custom'}<label class="grid gap-1 text-sm font-medium"
					>Custom {relationType === 'statement' ? 'predicate' : 'context role'}
					<span class="text-destructive">*</span><Input
						bind:value={customRelationLabel}
						placeholder={relationType === 'statement'
							? 'e.g. mentors, protects, suspects'
							: 'e.g. remembered from'}
					/></label
				>{/if}
			>
			<label class="grid gap-1 text-sm font-medium"
				>Description <span class="text-xs font-normal text-muted-foreground">(optional)</span
				><Textarea
					bind:value={relationDescription}
					placeholder="What does this connection mean in the story?"
				/></label
			>
			<label class="grid gap-1 text-sm font-medium"
				>Confidence <Input
					type="number"
					min="0"
					max="1"
					step="0.01"
					bind:value={relationConfidence}
				/></label
			>
			{#if relationType === 'context' && !pendingRelation?.hasContext}<p
					class="text-sm text-destructive"
				>
					Add or connect to a context node to create a contextual relation.
				</p>{/if}
		</div>
		<Dialog.Footer>
			{#if editingRelationId}<Button
					variant="destructive"
					disabled={creatingRelation}
					onclick={() => (deleteRelationDialogOpen = true)}>Remove relation</Button
			>{/if}
			<Button
				variant="outline"
				disabled={creatingRelation}
				onclick={() => (relationDialogOpen = false)}>Cancel</Button
			>
			<Button
				disabled={creatingRelation || (relationType === 'context' && !pendingRelation?.hasContext)}
				onclick={() => void createRelation()}
				>{creatingRelation ? 'Savingâ€¦' : editingRelationId ? 'Save relation' : 'Create relation'}</Button
			>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
<Dialog.Root bind:open={deleteRelationDialogOpen}>
	<Dialog.Content>
		<Dialog.Header>
			<Dialog.Title>Remove this connection?</Dialog.Title>
			<Dialog.Description>This removes the relation from the narrative graph.</Dialog.Description>
		</Dialog.Header>
		<Dialog.Footer>
			<Button variant="outline" disabled={deletingRelation} onclick={() => (deleteRelationDialogOpen = false)}>Cancel</Button>
			<Button variant="destructive" disabled={deletingRelation} onclick={() => void deleteRelation()}>{deletingRelation ? 'Removingâ€¦' : 'Remove relation'}</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
{#if message}<p
		class="fixed bottom-4 left-4 max-w-md rounded bg-foreground px-3 py-2 text-sm text-background"
	>
		{message}
	</p>{/if}
