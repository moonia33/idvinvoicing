<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api';
	import type { TaxBreakdown } from '#lib/types';
	import { fmtEur } from '#lib/format';
	import { Button } from '#lib/components/ui/button';
	import { Input } from '#lib/components/ui/input';
	import * as Card from '#lib/components/ui/card';
	import { Download } from '@lucide/svelte';

	let year = $state(new Date().getFullYear());
	let psdElsewhere = $state(false);
	let t = $state<TaxBreakdown | null>(null);

	async function load() {
		t = await api<TaxBreakdown>(`/taxes/summary?year=${year}&psd_paid_elsewhere=${psdElsewhere}`);
	}

	onMount(load);

	const METHOD_LABELS: Record<string, string> = {
		pct30: '30% pajamų',
		actual: 'Faktinės išlaidos'
	};
</script>

<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
	<h1 class="text-2xl font-semibold">Mokesčiai</h1>
	<div class="flex items-center gap-3">
		<Input type="number" class="w-24" bind:value={year} onchange={load} min="2000" />
		<label class="flex items-center gap-2 text-sm">
			<input type="checkbox" bind:checked={psdElsewhere} onchange={load} /> PSD mokamas kitur
		</label>
		<Button variant="outline" href="/api/v1/reports/taxes.xlsx?year={year}" target="_blank">
			<Download class="size-4" /> Excel
		</Button>
		<Button variant="outline" href="/api/v1/reports/journal.xlsx?year={year}" target="_blank">
			<Download class="size-4" /> Žurnalas (Excel)
		</Button>
	</div>
</div>

{#if t}
	{#each t.warnings as w (w)}
		<p class="mb-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{w}</p>
	{/each}

	<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
		<Card.Root
			><Card.Content class="pt-4"
				><div class="text-xs text-muted-foreground">Pajamos</div>
				<div class="text-xl font-semibold">{fmtEur(t.income_total)}</div></Card.Content
			></Card.Root
		>
		<Card.Root
			><Card.Content class="pt-4"
				><div class="text-xs text-muted-foreground">
					Atskaitymai ({METHOD_LABELS[t.deductions_method]})
				</div>
				<div class="text-xl font-semibold">{fmtEur(t.deductions_applied)}</div></Card.Content
			></Card.Root
		>
		<Card.Root
			><Card.Content class="pt-4"
				><div class="text-xs text-muted-foreground">Pelnas</div>
				<div class="text-xl font-semibold">{fmtEur(t.profit)}</div></Card.Content
			></Card.Root
		>
		<Card.Root
			><Card.Content class="pt-4"
				><div class="text-xs text-muted-foreground">Mokesčiai iš viso</div>
				<div class="text-xl font-semibold">{fmtEur(t.total)}</div></Card.Content
			></Card.Root
		>
	</div>

	{#if t.recommended_deductions_method !== t.deductions_method}
		<p class="mt-4 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800">
			Rekomendacija: naudoti „{METHOD_LABELS[t.recommended_deductions_method]}“ atskaitymus – tai
			palankiau.
		</p>
	{/if}

	<div class="mt-4 grid gap-4 lg:grid-cols-3">
		{#each [{ name: 'GPM', line: t.gpm }, { name: 'VSD', line: t.vsd }, { name: 'PSD', line: t.psd }] as item (item.name)}
			<Card.Root>
				<Card.Header><Card.Title class="text-base">{item.name}</Card.Title></Card.Header>
				<Card.Content class="space-y-1 text-sm">
					<div class="flex justify-between">
						<span class="text-muted-foreground">Bazė</span><span>{fmtEur(item.line.base)}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-muted-foreground">Tarifas</span><span
							>{(Number(item.line.rate) * 100).toFixed(2)}%</span
						>
					</div>
					<div class="flex justify-between font-semibold">
						<span>Suma</span><span>{fmtEur(item.line.amount)}</span>
					</div>
					{#if item.line.note}<p class="pt-1 text-xs text-muted-foreground">
							{item.line.note}
						</p>{/if}
				</Card.Content>
			</Card.Root>
		{/each}
	</div>
{:else}
	<p class="text-muted-foreground">Kraunama…</p>
{/if}
