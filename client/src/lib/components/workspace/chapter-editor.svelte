<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Editor } from '@tiptap/core';
	import StarterKit from '@tiptap/starter-kit';
	import { Button } from '$lib/components/ui/button';
	import type { TipTapDocument } from '$lib/features/narrative/types';

	let {
		document,
		readonly = false,
		highlight = '',
		onchange
	}: {
		document: TipTapDocument;
		readonly?: boolean;
		highlight?: string;
		onchange: (document: TipTapDocument, plainText: string) => void;
	} = $props();
	let host = $state<HTMLDivElement>();
	let editor: Editor | undefined;
	let lastDocument = '';

	function emitChange() {
		if (editor)
			onchange(editor.getJSON() as TipTapDocument, editor.getText({ blockSeparator: '\n\n' }));
	}

	onMount(() => {
		editor = new Editor({
			element: host,
			extensions: [StarterKit],
			content: document,
			editable: !readonly,
			onUpdate: emitChange
		});
		lastDocument = JSON.stringify(document);
		return () => editor?.destroy();
	});
	onDestroy(() => editor?.destroy());

	$effect(() => {
		const next = JSON.stringify(document);
		if (!editor || next === lastDocument) return;
		lastDocument = next;
		editor.commands.setContent(document, { emitUpdate: false });
	});

	$effect(() => {
		if (!editor || !highlight) return;
		const index = editor.getText({ blockSeparator: '\n\n' }).indexOf(highlight);
		if (index >= 0) {
			editor.commands.setTextSelection({ from: index + 1, to: index + highlight.length + 1 });
			editor.commands.scrollIntoView();
		}
	});
</script>

<div class="flex h-full min-h-0 flex-col rounded-xl border bg-card">
	{#if !readonly}
		<div class="flex gap-1 border-b p-2">
			<Button
				size="sm"
				variant="ghost"
				onclick={() => editor?.chain().focus().toggleBold().run()}
				aria-label="Bold">B</Button
			>
			<Button
				size="sm"
				variant="ghost"
				onclick={() => editor?.chain().focus().toggleItalic().run()}
				aria-label="Italic"><em>I</em></Button
			>
			<Button
				size="sm"
				variant="ghost"
				onclick={() => editor?.chain().focus().toggleBulletList().run()}
				aria-label="Bulleted list">• List</Button
			>
			<Button
				size="sm"
				variant="ghost"
				onclick={() => editor?.chain().focus().undo().run()}
				aria-label="Undo">Undo</Button
			>
		</div>
	{/if}
	<div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
		<div bind:this={host} class="prose prose-slate max-w-none focus:outline-none"></div>
	</div>
</div>
