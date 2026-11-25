<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api';
	import type { Transfer } from '#lib/types';
	import {
		fmtMoney,
		fmtDate,
		PAYMENT_METHODS,
		TRANSFER_STATUS_LABELS,
		TRANSFER_STATUS_VARIANTS
	} from '#lib/format';
	import { fromCents, queryString, toCents } from '#lib/allocate';
	import { Button } from '#lib/components/ui/button';
	import { Badge } from '#lib/components/ui/badge';
	import { Input } from '#lib/components/ui/input';
	import * as Card from '#lib/components/ui/card';
	import * as Table from '#lib/components/ui/table';
	import { cn } from '#lib/utils.js';

	const TABS = [
		{ key: 'all', label: 'Visi' },
		{ key: 'open', label: 'Nesudengti' },
		{ key: 'in', label: 'Gauti' },
		{ key: 'out', label: 'Sumokėti' },
		{ key: 'ignored', label: 'Neapskaitomi' }
	] as const;

	let transfers = $state<Transfer[]>([]);
	let tab = $state<string>('all');
	let dateFrom = $state('');
	let dateTo = $state('');
	let q = $state('');
	let loading = $state(true);

	async function load() {
		const qs = queryString({
			direction: tab === 'in' || tab === 'out' ? tab : '',
			status: tab === 'open' || tab === 'ignored' ? tab : '',
			date_from: dateFrom,
			date_to: dateTo,
			q: q.trim()
		});
		transfers = await api<Transfer[]>(`/transfers${qs}`);
		loading = false;
	}

	function sum(list: Transfer[], pick: (t: Transfer) => string): string {
		return fromCents(list.reduce((s, t) => s + toCents(pick(t)), 0));
	}

	let counted = $derived(transfers.filter((t) => !t.ignored && t.currency === 'EUR'));
	let totalIn = $derived(
		sum(
			counted.filter((t) => t.direction === 'in'),
			(t) => t.amount
		)
	);
	let totalOut = $derived(
		sum(
			counted.filter((t) => t.direction === 'out'),
			(t) => t.amount
		)
	);
	let totalOpen = $derived(sum(counted, (t) => t.unallocated));

	function setTab(key: string) {
		tab = key;
		load();
	}

	let searchTimer: ReturnType<typeof setTimeout>;
	function onSearch() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(load, 250);
	}

	onMount(load);
</script>

<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
	<h1 class="text-2xl font-semibold">Mokėjimai</h1>
	<div class="flex gap-2">
		<Button variant="outline" href={resolve('/payments/new') + '?direction=out'}>
			Naujas sumokėtas
		</Button>
		<Button href={resolve('/payments/new') + '?direction=in'}>Naujas gautas</Button>
	</div>
</div>

<div class="mb-4 grid gap-3 sm:grid-cols-3">
	<Card.Root>
		<Card.Content class="pt-5">
			<div class="text-sm text-muted-foreground">Gauta</div>
			<div class="text-xl font-semibold">{fmtMoney(totalIn)}</div>
		</Card.Content>
	</Card.Root>
	<Card.Root>
		<Card.Content class="pt-5">
			<div class="text-sm text-muted-foreground">Sumokėta</div>
			<div class="text-xl font-semibold">{fmtMoney(totalOut)}</div>
		</Card.Content>
	</Card.Root>
	<Card.Root>
		<Card.Content class="pt-5">
			<div class="text-sm text-muted-foreground">Nesudengta</div>
			<div class={cn('text-xl font-semibold', toCents(totalOpen) > 0 && 'text-destructive')}>
				{fmtMoney(totalOpen)}
			</div>
		</Card.Content>
	</Card.Root>
</div>

<div class="mb-4 flex flex-wrap items-center gap-3">
	<div class="inline-flex rounded-md border p-0.5" role="tablist">
		{#each TABS as t (t.key)}
			<button
				type="button"
				role="tab"
				aria-selected={tab === t.key}
				class={cn(
					'rounded px-3 py-1.5 text-sm transition-colors',
					tab === t.key ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
				)}
				onclick={() => setTab(t.key)}>{t.label}</button
			>
		{/each}
	</div>
	<Input type="date" class="w-40" bind:value={dateFrom} onchange={load} aria-label="Nuo" />
	<span class="text-muted-foreground">–</span>
	<Input type="date" class="w-40" bind:value={dateTo} onchange={load} aria-label="Iki" />
	<Input
		class="w-64"
		placeholder="Kontragentas, paskirtis…"
		bind:value={q}
		oninput={onSearch}
		aria-label="Paieška"
	/>
</div>

<Card.Root>
	<Table.Root>
		<Table.Header>
			<Table.Row>
				<Table.Head>Data</Table.Head>
				<Table.Head>Kontragentas</Table.Head>
				<Table.Head>Paskirtis / dokumentai</Table.Head>
				<Table.Head>Būdas</Table.Head>
				<Table.Head>Būsena</Table.Head>
				<Table.Head class="text-right">Suma</Table.Head>
				<Table.Head class="text-right">Nesudengta</Table.Head>
			</Table.Row>
		</Table.Header>
		<Table.Body>
			{#each transfers as t (t.id)}
				<Table.Row
					class="cursor-pointer"
					onclick={() => goto(resolve('/payments/[id]', { id: String(t.id) }))}
				>
					<Table.Cell class="whitespace-nowrap">{fmtDate(t.date)}</Table.Cell>
					<Table.Cell class="font-medium">{t.counterparty_display || '–'}</Table.Cell>
					<Table.Cell class="max-w-xs truncate text-sm text-muted-foreground">
						{t.allocations.map((a) => a.document_label).join(', ') || t.reference || t.note}
					</Table.Cell>
					<Table.Cell class="text-sm">{PAYMENT_METHODS[t.method]}</Table.Cell>
					<Table.Cell>
						<Badge variant={TRANSFER_STATUS_VARIANTS[t.status]}>
							{TRANSFER_STATUS_LABELS[t.status]}
						</Badge>
					</Table.Cell>
					<Table.Cell
						class={cn(
							'text-right whitespace-nowrap tabular-nums',
							t.direction === 'in' ? 'text-emerald-700' : ''
						)}
					>
						{t.direction === 'in' ? '+' : '−'}{fmtMoney(t.amount, t.currency)}
					</Table.Cell>
					<Table.Cell class="text-right whitespace-nowrap tabular-nums">
						{t.ignored || toCents(t.unallocated) === 0 ? '–' : fmtMoney(t.unallocated, t.currency)}
					</Table.Cell>
				</Table.Row>
			{/each}
			{#if !loading && transfers.length === 0}
				<Table.Row>
					<Table.Cell colspan={7} class="text-center text-muted-foreground">
						Mokėjimų nėra
					</Table.Cell>
				</Table.Row>
			{/if}
		</Table.Body>
	</Table.Root>
</Card.Root>
