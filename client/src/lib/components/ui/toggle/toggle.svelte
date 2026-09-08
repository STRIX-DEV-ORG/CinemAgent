<script lang="ts">
	let {
		checked = false,
		disabled = false,
		label,
		description,
		oncheckedchange
	}: {
		checked?: boolean;
		disabled?: boolean;
		label: string;
		description?: string;
		oncheckedchange?: (checked: boolean) => void;
	} = $props();
</script>

<button
	type="button"
	role="switch"
	aria-checked={checked}
	{disabled}
	class="flex w-full cursor-pointer items-center justify-between gap-4 rounded-lg border bg-card px-4 py-3 text-left transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
	onclick={() => oncheckedchange?.(!checked)}
>
	<span>
		<span class="block text-sm font-medium">{label}</span>
		{#if description}
			<span class="mt-0.5 block text-xs text-muted-foreground">{description}</span>
		{/if}
	</span>
	<span class={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${checked ? 'bg-primary' : 'bg-muted-foreground/30'}`}>
		<span class={`absolute top-0.5 size-5 rounded-full bg-background shadow-sm transition-transform ${checked ? 'translate-x-5' : 'translate-x-0.5'}`}></span>
	</span>
</button>
