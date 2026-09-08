<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { onDestroy, onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import { Textarea } from '$lib/components/ui/textarea';
	import * as Dialog from '$lib/components/ui/dialog';
	import { narrativeApi, workspaceApi } from '$lib/features/narrative/api';
	import { entityTypeOptions } from '$lib/features/narrative/node-options';
	import type {
		AnalysisProposal,
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

	let { params } = $props();
	let chapter = $state<StoryChapter | null>(null);
	let chapters = $state<StoryChapter[]>([]);
	let chapterTitleDraft = $state('');
	let editingChapterTitle = $state(false);
	let savingChapterTitle = $state(false);
	let subgraph = $state<Subgraph | null>(null);
	let proposals = $state<AnalysisProposal[]>([]);
	let selectedProposalIds = $state<string[]>([]);
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
	let nodeFormAliases = $state('');
	let nodeFormHolder = $state('');
	let nodeFormOrigin = $state('writer');
	let nodeFormConfidence = $state('1');
	let metadataEntries = $state<Array<{ key: string; value: string }>>([{ key: '', value: '' }]);
	let preservedMetadata = $state<Record<string, unknown>>({});
	let analyzing = $state(false);
	let proposingText = $state(false);
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

	async function load() {
		try {
			[chapter, subgraph, chapters] = await Promise.all([
				workspaceApi.getChapter(params.graphId, params.chapterId),
				narrativeApi.querySubgraph(params.graphId, false, [], params.chapterId),
				workspaceApi.listChapters(params.graphId)
			]);
			chapterQuery = chapter.title;
			chapterTitleDraft = chapter.title;
		} catch (error) {
			message = error instanceof Error ? error.message : 'Could not load chapter.';
		}
	}
	onMount(() => void load());
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
	async function apply() {
		if (!proposals.length || !runId) return;
		const batch = await workspaceApi.applyProposals(
			params.graphId,
			params.chapterId,
			runId,
			selectedProposalIds
		);
		message = `Batch ${(await waitForBatch(batch.id)).status}.`;
		proposals = [];
		runId = null;
		await load();
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
		const changes: Record<string, unknown> = { confidence, metadata };
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
				type: nodeFormType.trim(),
				description: nodeFormDescription,
				holder_entity_id: nodeFormHolder.trim() || null
			});
		} else {
			Object.assign(changes, {
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
		relationDialogOpen = true;
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
			const batch = await narrativeApi.createRelation(
				params.graphId,
				params.chapterId,
				pendingRelation.sourceId,
				pendingRelation.targetId,
				{
					relationType,
					label,
					description: relationDescription,
					confidence
				}
			);
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
	async function waitForBatch(batchId: string) {
		for (let attempt = 0; attempt < 12; attempt += 1) {
			await new Promise((resolve) => setTimeout(resolve, 500));
			const batch = await narrativeApi.getBatch(params.graphId, batchId);
			if (!['accepted', 'applying'].includes(batch.status)) return batch;
		}
		return narrativeApi.getBatch(params.graphId, batchId);
	}
</script>

<main class="grid h-screen min-h-0 grid-cols-[3.5rem_minmax(0,1fr)_minmax(0,1fr)] bg-background">
	<aside class="flex flex-col items-center gap-3 border-r py-4">
		<StoryMenu graphId={params.graphId} compact />
		<ToolToggle
			label="Extract graph proposals from chapter text"
			toggleable={false}
			disabled={analyzing}
			onclick={() => void analyze()}>{analyzing ? '…' : '✦'}</ToolToggle
		>
		<ToolToggle
			label="Suggest prose from the chapter graph"
			toggleable={false}
			disabled={proposingText}
			onclick={() => void proposeTextFromGraph()}>{proposingText ? '…' : '✎'}</ToolToggle
		>
		<ToolToggle label="Image generation is coming soon" disabled>▧</ToolToggle>
		<ToolToggle label="More AI tools coming soon" disabled>⋯</ToolToggle>
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
					{#if selectedNodeKind === 'entity' || selectedNodeKind === 'event'}<label
							class="grid gap-1 text-sm">Name<Input bind:value={nodeFormName} /></label
						>{/if}
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
						>{:else}<label class="grid gap-1 text-sm">Type<Input bind:value={nodeFormType} /></label
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
			<NarrativeCanvas {subgraph} onselect={selectNode} onconnect={beginRelation} />
		</div>
		{#if nodeSidebarOpen}<NodeCreateSidebar
				creating={creatingNode}
				{existingNodes}
				onclose={() => (nodeSidebarOpen = false)}
				oncreate={(kind, values) => void createNode(kind, values)}
				onlink={(id, nodeType) => void linkExistingNode(id, nodeType)}
			/>{/if}
		{#if proposals.length}<aside class="max-h-56 overflow-y-auto border-t bg-card p-4">
				<div class="mb-2 flex items-center justify-between">
					<strong>Extracted graph proposals</strong><Button size="sm" onclick={() => void apply()}
						>Apply selected</Button
					>
				</div>
				{#each proposals as proposal (proposal.id)}<label class="flex gap-2 py-2 text-sm"
						><input
							type="checkbox"
							checked={selectedProposalIds.includes(proposal.id)}
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
			</aside>{/if}
	</section>
</main>
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
				>{:else}<label class="grid gap-1 text-sm">Type<Input bind:value={nodeFormType} /></label
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
			<Dialog.Title>Describe this connection</Dialog.Title>
			<Dialog.Description>
				{pendingRelation?.sourceLabel ?? 'Source'} â†’ {pendingRelation?.targetLabel ?? 'Target'}
			</Dialog.Description>
		</Dialog.Header>
		<div class="grid gap-4">
			<label class="grid gap-1 text-sm font-medium"
				>Relation kind<select
					class="h-9 rounded-md border bg-background px-2"
					value={relationType}
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
			<Button
				variant="outline"
				disabled={creatingRelation}
				onclick={() => (relationDialogOpen = false)}>Cancel</Button
			>
			<Button
				disabled={creatingRelation || (relationType === 'context' && !pendingRelation?.hasContext)}
				onclick={() => void createRelation()}
				>{creatingRelation ? 'Creatingâ€¦' : 'Create relation'}</Button
			>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
{#if message}<p
		class="fixed bottom-4 left-4 max-w-md rounded bg-foreground px-3 py-2 text-sm text-background"
	>
		{message}
	</p>{/if}
