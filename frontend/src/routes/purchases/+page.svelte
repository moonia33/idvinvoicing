<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api';
	import type { Purchase } from '#lib/types';
	import { fmtEur, fmtDate, PURCHASE_STATUS_LABELS } from '#lib/format';
	import { Button } from '#lib/components/ui/button';
	import { Badge } from '#lib/components/ui/badge';
	import * as Card from '#lib/components/ui/card';
	import * as Table from '#lib/components/ui/table';
	import * as Select from '#lib/components/ui/select';

	let purchases = $state<Purchase[]>([]);
	let statusFilter = $state('all');

	const paidEur = (p: Purchase) =>
		p.payments.reduce((s, pay) => s + Number(pay.amount_eur ?? 0), 0).toFixed(2);

	async function load() {
		const q = statusFilter !== 'all' ? `?status=${statusFilter}` : '';
		purchases = await api<Purchase[]>(`/purchases${q}`);
	}

	onMount(load);
</script>

<div class="mb-6 flex items-center justify-between">
	<h1 class="text-2xl font-semibold">Pirkimai</h1>
	<div class="flex items-center gap-3">
		<Select.Root type="single" bind:value={statusFilter} onValueChange={() => load()}>
			<Select.Trigger class="w-44">
				{statusFilter === 'all' ? 'Visi statusai' : PURCHASE_STATUS_LABELS[statusFilter]}
			</Select.Trigger>
			<Select.Content>
				<Select.Item value="all" label="Visi">Visi</Select.Item>
				{#each Object.entries(PURCHASE_STATUS_LABELS) as [v, l] (v)}
					<Select.Item value={v} label={l}>{l}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>
		<Button href="/purchases/new">Naujas pirkinys</Button>
	</div>
</div>

<Card.Root>
	<Table.Root>
		<Table.Header>
			<Table.Row>
				<Table.Head>Dok. nr.</Table.Head>
				<Table.Head>Tiekėjas</Table.Head>
				<Table.Head>Data</Table.Head>
				<Table.Head>Apmokėti iki</Table.Head>
				<Table.Head>Statusas</Table.Head>
				<Table.Head class="text-right">Suma</Table.Head>
				<Table.Head class="text-right">Apmokėta</Table.Head>
			</Table.Row>
		</Table.Header>
		<Table.Body>
			{#each purchases as p (p.id)}
				<Table.Row
					class="cursor-pointer"
					onclick={() => (window.location.href = `/purchases/${p.id}`)}
				>
					<Table.Cell class="font-medium">{p.doc_number || '–'}</Table.Cell>
					<Table.Cell>{p.supplier.name}</Table.Cell>
					<Table.Cell>{fmtDate(p.document_date)}</Table.Cell>
					<Table.Cell>{fmtDate(p.due_date)}</Table.Cell>
					<Table.Cell
						><Badge
							variant={p.status === 'paid'
								? 'default'
								: p.status === 'cancelled'
									? 'destructive'
									: 'secondary'}>{PURCHASE_STATUS_LABELS[p.status]}</Badge
						></Table.Cell
					>
					<Table.Cell class="text-right">
						{fmtEur(p.total_eur)}
						{#if p.currency !== 'EUR'}<span class="text-xs text-muted-foreground"
								>({p.total} {p.currency})</span
							>{/if}
					</Table.Cell>
					<Table.Cell class="text-right">{fmtEur(paidEur(p))}</Table.Cell>
				</Table.Row>
			{/each}
			{#if purchases.length === 0}
				<Table.Row
					><Table.Cell colspan={7} class="text-center text-muted-foreground"
						>Pirkimų nėra</Table.Cell
					></Table.Row
				>
			{/if}
		</Table.Body>
	</Table.Root>
</Card.Root>
