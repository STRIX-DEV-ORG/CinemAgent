<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Accordion } from '$lib/components/ui/accordion';
	import { contextTypeOptions, entityTypeOptions, eventTypeOptions } from '$lib/features/narrative/node-options';

	type NodeKind = 'entity' | 'event' | 'context' | 'assumption';

	let {
		creating = false,
		existingNodes = [],
		onclose,
		oncreate,
		onlink
	}: {
		creating?: boolean;
		existingNodes?: Array<{
			id: string;
			label: string;
			nodeType: 'entity' | 'event' | 'context' | 'knowledge_element';
		}>;
		onclose: () => void;
		oncreate: (kind: NodeKind, values: Record<string, unknown>) => void;
		onlink: (id: string, nodeType: 'entity' | 'event' | 'context' | 'knowledge_element') => void;
	} = $props();

	let kind = $state<NodeKind>('entity');
	let name = $state('');
	let type = $state('character');
	let status = $state('active');
	let aliases = $state('');
	let description = $state('');
	let content = $state('');
	let holderEntityId = $state('');
	let elementType = $state('assumption');
	let origin = $state('writer');
	let confidence = $state('1');
	let error = $state('');
	let existingSearch = $state('');
	const matchingExistingNodes = $derived(
		existingNodes.filter((node) => node.label.toLowerCase().includes(existingSearch.toLowerCase()))
	);

	function changeKind(next: NodeKind) {
		kind = next;
		error = '';
		if (next === 'entity') type = 'character';
		if (next === 'event') type = 'story_event';
		if (next === 'context') type = 'setting';
	}

	function submit() {
		const required = name.trim() && (kind === 'assumption' ? elementType.trim() : type.trim());
		if (!required) {
			error = 'Complete the required fields before creating this node.';
			return;
		}
		const numericConfidence = Number(confidence);
		if (!Number.isFinite(numericConfidence) || numericConfidence < 0 || numericConfidence > 1) {
			error = 'Confidence must be a number from 0 to 1.';
			return;
		}
		oncreate(kind, {
			name: name.trim(),
			type: type.trim(),
			status,
			aliases: aliases
				.split(',')
				.map((alias) => alias.trim())
				.filter(Boolean),
			description: description.trim(),
			content: content.trim(),
			holder_entity_id: holderEntityId.trim() || null,
			element_type: elementType.trim(),
			origin: origin.trim() || 'writer',
			confidence: numericConfidence
		});
	}
</script>

<aside
	class="absolute inset-y-0 right-0 z-30 w-96 overflow-y-auto border-l bg-background p-5 shadow-xl"
>
	<div class="mb-5 flex items-center justify-between">
		<div>
			<p class="text-xs text-muted-foreground">Narrative graph</p>
			<h2 class="font-semibold">New node</h2>
		</div>
		<Button size="sm" variant="ghost" onclick={onclose}>Close</Button>
	</div>
	<Accordion label="Add an existing node" class="mb-5">
		<p class="mb-2 text-xs text-muted-foreground">
			Global nodes can appear in more than one chapter.
		</p>
		<Input bind:value={existingSearch} placeholder="Search story nodes…" />
		<div class="mt-2 max-h-36 space-y-1 overflow-y-auto">
			{#each matchingExistingNodes as node (node.id)}<button
					class="flex w-full items-center justify-between rounded px-2 py-1 text-left text-sm hover:bg-muted"
					onclick={() => onlink(node.id, node.nodeType)}
					><span>{node.label}</span><span class="text-xs text-muted-foreground">Add</span></button
				>{:else}<p class="text-xs text-muted-foreground">No available nodes.</p>{/each}
		</div>
	</Accordion>
	<label class="grid gap-1 text-sm font-medium"
		>Node type
		<select
			class="h-9 rounded-md border bg-background px-2"
			value={kind}
			onchange={(event) => changeKind(event.currentTarget.value as NodeKind)}
		>
			<option value="entity">Entity</option><option value="event">Event</option><option
				value="context">Context</option
			><option value="assumption">Knowledge element</option>
		</select>
	</label>
	<div class="mt-4 grid gap-4">
		<label class="grid gap-1 text-sm"
				>Name <span class="text-destructive">*</span><Input
					bind:value={name}
					placeholder={kind === 'entity' ? 'e.g. Mara Voss' : kind === 'context' ? 'e.g. Winter Court' : kind === 'event' ? 'e.g. The arrival' : 'e.g. The hidden oath'}
				/></label
			>
		{#if kind === 'entity'}<label class="grid gap-1 text-sm"
				>Entity type <span class="text-destructive">*</span><select
					class="h-9 rounded-md border bg-background px-2"
					bind:value={type}
					>{#each entityTypeOptions as option}<option value={option.value}>{option.label}</option
						>{/each}</select
				></label
			>{:else if kind === 'event'}<label class="grid gap-1 text-sm"
				>Event type <span class="text-destructive">*</span><select class="h-9 rounded-md border bg-background px-2" bind:value={type}
					>{#each eventTypeOptions as option}<option value={option.value}>{option.label}</option>{/each}</select
				></label
			>{:else if kind === 'context'}<label class="grid gap-1 text-sm"
				>Context type <span class="text-destructive">*</span><select class="h-9 rounded-md border bg-background px-2" bind:value={type}
					>{#each contextTypeOptions as option}<option value={option.value}>{option.label}</option>{/each}</select
				></label
			>{/if}
		{#if kind !== 'context'}<label class="grid gap-1 text-sm"
				>Status<select class="h-9 rounded-md border bg-background px-2" bind:value={status}
					><option value="active">Active</option><option value="draft">Draft</option><option
						value="inactive">Inactive</option
					></select
				></label
			>{/if}
		{#if kind === 'entity'}<label class="grid gap-1 text-sm"
				>Aliases <span class="text-xs text-muted-foreground">(optional, comma separated)</span
				><Input bind:value={aliases} placeholder="e.g. The Captain, M. Voss" /></label
			>{/if}
		<label class="grid gap-1 text-sm"
				>Content <span class="text-xs text-muted-foreground">(what this node says or contains)</span><Textarea
					bind:value={content}
					placeholder="The important story detail, fact, or scene information"
				/></label
			>
		{#if kind === 'entity' || kind === 'event' || kind === 'context' || kind === 'assumption'}<label
				class="grid gap-1 text-sm"
				>Description <span class="text-xs text-muted-foreground">(optional)</span><Textarea
					bind:value={description}
				/></label
			>{/if}
		{#if kind === 'context'}<label class="grid gap-1 text-sm"
				>Holder entity ID <span class="text-xs text-muted-foreground">(optional)</span><Input
					bind:value={holderEntityId}
					placeholder="Entity UUID"
				/></label
			>{/if}
		{#if kind === 'assumption'}<label class="grid gap-1 text-sm"
				>Element type <span class="text-destructive">*</span><select
					class="h-9 rounded-md border bg-background px-2"
					bind:value={elementType}
					><option value="assumption">Assumption</option><option value="attribute">Attribute</option
					><option value="constraint">Constraint</option><option value="fact">Fact</option><option
						value="note">Note</option
					></select
				></label
			><label class="grid gap-1 text-sm"
				>Origin <span class="text-xs text-muted-foreground">(optional)</span><Input
					bind:value={origin}
				/></label
			>{/if}
		<label class="grid gap-1 text-sm"
			>Confidence <span class="text-xs text-muted-foreground">(optional)</span><Input
				type="number"
				min="0"
				max="1"
				step="0.01"
				bind:value={confidence}
			/></label
		>
	</div>
	{#if error}<p class="mt-3 text-sm text-destructive">{error}</p>{/if}
	<div class="mt-6 flex gap-2">
		<Button class="flex-1" disabled={creating} onclick={submit}
			>{creating ? 'Creating…' : 'Create node'}</Button
		><Button variant="outline" disabled={creating} onclick={onclose}>Cancel</Button>
	</div>
</aside>
