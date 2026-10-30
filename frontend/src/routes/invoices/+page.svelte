<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api';
	import type { Invoice } from '#lib/types';
	import { fmtEur, fmtDate, STATUS_LABELS } from '#lib/format';
	import { Button } from '#lib/components/ui/button';
	import { Badge } from '#lib/components/ui/badge';
	import * as Card from '#lib/components/ui/card';
	import * as Table from '#lib/components/ui/table';
	import * as Select from '#lib/components/ui/select';

	let invoices = $state<Invoice[]>([]);
	let statusFilter = $state('');

	async function load() {
		const q = statusFilter ? `?status=${statusFilter}` : '';
		invoices = await api<Invoice[]>(`/invoices${q}`);
	}

	onMount(load);
</script>

<div class="mb-6 flex items-center justify-between">
	<h1 class="text-2xl font-semibold">Sąskaitos</h1>
	<div class="flex items-center gap-3">
		<Select.Root type="single" bind:value={statusFilter} onValueChange={() => load()}>
			<Select.Trigger class="w-44">
				{statusFilter ? STATUS_LABELS[statusFilter] : 'Visi statusai'}
			</Select.Trigger>
			<Select.Content>
				<Select.Item value="" label="Visi">Visi</Select.Item>
				{#each Object.entries(STATUS_LABELS) as [v, l] (v)}
					<Select.Item value={v} label={l}>{l}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>
		<Button href="/invoices/new">Nauja sąskaita</Button>
	</div>
</div>

<Card.Root>
	<Table.Root>
		<Table.Header>
			<Table.Row>
				<Table.Head>Numeris</Table.Head>
				<Table.Head>Klientas</Table.Head>
				<Table.Head>Išrašyta</Table.Head>
				<Table.Head>Apmokėti iki</Table.Head>
				<Table.Head>Statusas</Table.Head>
				<Table.Head class="text-right">Suma</Table.Head>
			</Table.Row>
		</Table.Header>
		<Table.Body>
			{#each invoices as inv (inv.id)}
				<Table.Row
					class="cursor-pointer"
					onclick={() => (window.location.href = `/invoices/${inv.id}`)}
				>
					<Table.Cell class="font-medium">{inv.full_number ?? 'Juodraštis'}</Table.Cell>
					<Table.Cell>{inv.client.name}</Table.Cell>
					<Table.Cell>{fmtDate(inv.issue_date)}</Table.Cell>
					<Table.Cell>{fmtDate(inv.due_date)}</Table.Cell>
					<Table.Cell
						><Badge
							variant={inv.status === 'paid'
								? 'default'
								: inv.status === 'cancelled'
									? 'destructive'
									: 'secondary'}>{STATUS_LABELS[inv.status]}</Badge
						></Table.Cell
					>
					<Table.Cell class="text-right">{fmtEur(inv.total)}</Table.Cell>
				</Table.Row>
			{/each}
			{#if invoices.length === 0}
				<Table.Row
					><Table.Cell colspan={6} class="text-center text-muted-foreground"
						>Sąskaitų nėra</Table.Cell
					></Table.Row
				>
			{/if}
		</Table.Body>
	</Table.Root>
</Card.Root>
