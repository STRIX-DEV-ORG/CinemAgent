<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		label,
		pressed = $bindable(false),
		toggleable = true,
		disabled = false,
		onclick,
		children
	}: {
		label: string;
		pressed?: boolean;
		toggleable?: boolean;
		disabled?: boolean;
		onclick?: (event: MouseEvent) => void;
		children: Snippet;
	} = $props();

	function toggle(event: MouseEvent) {
		if (disabled) return;
		if (toggleable) pressed = !pressed;
		onclick?.(event);
	}
</script>

<div class="group relative flex justify-center">
	<button
		type="button"
		class="flex size-8 items-center justify-center rounded-lg text-sm transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50 aria-pressed:bg-primary aria-pressed:text-primary-foreground"
		aria-label={label}
		aria-pressed={pressed}
		{disabled}
		onclick={toggle}
	>
		{@render children()}
	</button>
	<span
		role="tooltip"
		class="pointer-events-none absolute top-1/2 left-full z-30 ml-2 w-max -translate-y-1/2 rounded bg-foreground px-2 py-1 text-xs text-background opacity-0 shadow-sm transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
		>{label}</span
	>
</div>
