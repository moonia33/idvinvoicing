<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api';
	import type { TaxBreakdown } from '#lib/types';
	import { fmtEur } from '#lib/format';
	import { Button } from '#lib/components/ui/button';
	import { Input } from '#lib/components/ui/input';
	import * as Card from '#lib/components/ui/card';
	import * as Select from '#lib/components/ui/select';
	import * as Table from '#lib/components/ui/table';
	import { Download } from '@lucide/svelte';

	const now = new Date();
	let year = $state(now.getFullYear());
	let month = $state('auto'); // 'auto' arba 1-12
	let t = $state<TaxBreakdown | null>(null);

	async function load() {
		const m = month === 'auto' ? '' : `&months=${month}`;
		t = await api<TaxBreakdown>(`/taxes/summary?year=${year}${m}`);
	}

	onMount(load);

	const METHOD_LABELS: Record<string, string> = {
		pct30: '30% pajamų',
		actual: 'Faktinės išlaidos'
	};
	const MONTH_NAMES = [
		'',
		'Sausis',
		'Vasaris',
		'Kovas',
		'Balandis',
		'Gegužė',
		'Birželis',
		'Liepa',
		'Rugpjūtis',
		'Rugsėjis',
		'Spalis',
		'Lapkritis',
		'Gruodis'
	];
</script>

<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
	<h1 class="text-2xl font-semibold">Mokesčiai</h1>
	<div class="flex flex-wrap items-center gap-3">
		<Input type="number" class="w-24" bind:value={year} onchange={load} min="2000" />
		<Select.Root
			type="single"
			value={month}
			onValueChange={(v) => {
				month = v;
				load();
			}}
		>
			<Select.Trigger class="w-40">
				{month === 'auto' ? `Auto (${now.getMonth() + 1} mėn.)` : `${month} mėn.`}
			</Select.Trigger>
			<Select.Content>
				<Select.Item value="auto" label="Auto">Auto (einamasis mėn.)</Select.Item>
				{#each Array.from({ length: 12 }, (_, i) => i + 1) as m (m)}
					<Select.Item value={String(m)} label="{m} mėn.">{MONTH_NAMES[m]}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>
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
	<p class="mb-4 text-sm text-muted-foreground">
		Skaičiuojama už {t.months}
		{t.months === 1 ? 'mėnesį' : 'mėnesius'} ({t.year} m.)
	</p>

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
				<div class="text-xl font-semibold">{fmtEur(t.total)}</div>
				<div class="mt-1 text-xs text-muted-foreground">
					Sumokėta {fmtEur(t.paid_total)} · Liko {fmtEur(t.remaining_total)}
				</div></Card.Content
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
						<span>Apskaičiuota</span><span>{fmtEur(item.line.amount)}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-muted-foreground">Sumokėta</span><span>{fmtEur(item.line.paid)}</span>
					</div>
					<div class="flex justify-between font-semibold">
						<span>Liko mokėti</span><span>{fmtEur(item.line.remaining)}</span>
					</div>
					{#if item.line.note}<p class="pt-1 text-xs text-muted-foreground">
							{item.line.note}
						</p>{/if}
				</Card.Content>
			</Card.Root>
		{/each}
	</div>

	{#if t.monthly.length}
		<Card.Root class="mt-4">
			<Card.Header><Card.Title class="text-base">Mėnesių suvestinė</Card.Title></Card.Header>
			<Card.Content class="p-0">
				<Table.Root>
					<Table.Header>
						<Table.Row>
							<Table.Head>Mėnuo</Table.Head>
							<Table.Head class="text-right">Pajamos</Table.Head>
							<Table.Head class="text-right">Pelnas</Table.Head>
							<Table.Head class="text-right">VSD įmoka</Table.Head>
							<Table.Head class="text-right">PSD įmoka</Table.Head>
						</Table.Row>
					</Table.Header>
					<Table.Body>
						{#each t.monthly as m (m.month)}
							<Table.Row>
								<Table.Cell>{MONTH_NAMES[m.month]}</Table.Cell>
								<Table.Cell class="text-right">{fmtEur(m.income)}</Table.Cell>
								<Table.Cell class="text-right">{fmtEur(m.profit)}</Table.Cell>
								<Table.Cell class="text-right">{fmtEur(m.vsd)}</Table.Cell>
								<Table.Cell class="text-right">{fmtEur(m.psd)}</Table.Cell>
							</Table.Row>
						{/each}
					</Table.Body>
				</Table.Root>
				<p class="px-4 pt-1 pb-3 text-xs text-muted-foreground">
					VSD/PSD – mėnesinės įmokos; draustiems kitur – be MMA minimumo (metų gale nuo 90 % pelno
					vis tiek perskaičiuojami).
				</p>
			</Card.Content>
		</Card.Root>
	{/if}
{:else}
	<p class="text-muted-foreground">Kraunama…</p>
{/if}
