<script lang="ts">
	import type { NodeProps } from '@xyflow/svelte';
	import { Handle, Position } from '@xyflow/svelte';
	let { data }: NodeProps = $props();
	const record = $derived((data.record ?? {}) as Record<string, unknown>);
	const kind = $derived(String(data.kind ?? 'node'));
	const colorClass = $derived(
		({
			entity: 'border-blue-400/70 bg-blue-50 text-blue-800 hover:border-blue-500 hover:bg-blue-100 dark:bg-blue-950/30 dark:text-blue-200',
			event: 'border-amber-400/70 bg-amber-50 text-amber-900 hover:border-amber-500 hover:bg-amber-100 dark:bg-amber-950/30 dark:text-amber-200',
			context: 'border-violet-400/70 bg-violet-50 text-violet-900 hover:border-violet-500 hover:bg-violet-100 dark:bg-violet-950/30 dark:text-violet-200',
			knowledge: 'border-emerald-400/70 bg-emerald-50 text-emerald-900 hover:border-emerald-500 hover:bg-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-200',
			chapter: 'border-slate-400/70 bg-slate-50 text-slate-900 hover:border-slate-500 hover:bg-slate-100 dark:bg-slate-950/30 dark:text-slate-200'
		})[kind] ?? 'border-border bg-card text-card-foreground hover:border-primary/60 hover:bg-primary/5'
	);
</script>

{#if data.connectable !== false}
	<Handle type="target" position={Position.Top} />
	<Handle type="target" position={Position.Left} id="left" />
{/if}
<article
	class={`box-border flex h-[104px] w-[240px] cursor-pointer flex-col overflow-hidden rounded-lg border px-3 py-2 shadow-sm transition duration-150 ease-out hover:-translate-y-0.5 hover:shadow-md ${colorClass}`}
>
	<p class="text-[0.65rem] font-semibold tracking-wide uppercase opacity-80">
		{kind}
	</p>
	<p class="mt-1 overflow-hidden break-words text-sm font-medium">{String(data.label)}</p>
	{#if record.content || record.description}
		<p class="mt-1 line-clamp-2 overflow-hidden break-words text-xs opacity-75">
			{String(record.content || record.description)}
		</p>
	{/if}
</article>
{#if data.connectable !== false}
	<Handle type="source" position={Position.Bottom} />
	<Handle type="source" position={Position.Right} id="right" />
{/if}
