import { browser } from '$app/environment';
import type { NarrativeGraph } from './types';

const storageKey = 'cinemagent.recent-graphs';
export function loadRecentGraphs(): NarrativeGraph[] {
	if (!browser) return [];
	try {
		return JSON.parse(localStorage.getItem(storageKey) ?? '[]') as NarrativeGraph[];
	} catch {
		return [];
	}
}
export function rememberGraph(graph: NarrativeGraph): NarrativeGraph[] {
	const graphs = [graph, ...loadRecentGraphs().filter((item) => item.id !== graph.id)].slice(0, 8);
	if (browser) localStorage.setItem(storageKey, JSON.stringify(graphs));
	return graphs;
}
export function forgetGraph(graphId: string): NarrativeGraph[] {
	const normalizedId = String(graphId).toLowerCase();
	const graphs = loadRecentGraphs().filter((item) => String(item.id).toLowerCase() !== normalizedId);
	if (browser) localStorage.setItem(storageKey, JSON.stringify(graphs));
	return graphs;
}
