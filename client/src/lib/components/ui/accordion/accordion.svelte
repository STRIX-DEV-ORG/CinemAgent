<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		label,
		open = $bindable(false),
		class: className = '',
		children
	}: { label: string; open?: boolean; class?: string; children: Snippet } = $props();
</script>

<section class={`rounded-md border ${className}`}>
	<button
		type="button"
		class="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium hover:bg-muted"
		aria-expanded={open}
		onclick={() => (open = !open)}
	>
		{label}<span aria-hidden="true">{open ? '−' : '+'}</span>
	</button>
	{#if open}<div class="border-t p-3">{@render children()}</div>{/if}
</section>
