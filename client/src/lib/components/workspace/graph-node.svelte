<script lang="ts">
	import type { NodeProps } from '@xyflow/svelte';
	import { Handle, Position } from '@xyflow/svelte';
	let { data }: NodeProps = $props();
</script>

<Handle type="target" position={Position.Top} />
<Handle type="target" position={Position.Left} id="left" />
<article
	class="min-w-36 cursor-pointer rounded-lg border bg-card px-3 py-2 shadow-sm transition duration-150 ease-out hover:-translate-y-0.5 hover:border-primary/60 hover:bg-primary/5 hover:shadow-md"
>
	<p class="text-[0.65rem] font-semibold tracking-wide text-primary uppercase">
		{String(data.kind ?? 'node')}
	</p>
	<p class="mt-1 text-sm font-medium">{String(data.label)}</p>
</article>
<Handle type="source" position={Position.Bottom} />
<Handle type="source" position={Position.Right} id="right" />
