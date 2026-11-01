<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api';
	import { resolve } from '$app/paths';
	import { fmtEur } from '#lib/format';
	import * as Card from '#lib/components/ui/card';
	import type { Journal, TaxBreakdown, Invoice } from '#lib/types';
	import { Badge } from '#lib/components/ui/badge';
	import { STATUS_LABELS } from '#lib/format';

	const year = new Date().getFullYear();
	let journal = $state<Journal | null>(null);
	let taxes = $state<TaxBreakdown | null>(null);
	let unpaid = $state<Invoice[]>([]);

	onMount(async () => {
		const [j, t, inv] = await Promise.all([
			api<Journal>(`/ledger/journal?year=${year}&month=${new Date().getMonth() + 1}`),
			api<TaxBreakdown>(`/taxes/summary?year=${year}`),
			api<Invoice[]>('/invoices?status=issued')
		]);
		journal = j;
		taxes = t;
		unpaid = inv.slice(0, 6);
	});
</script>

<h1 class="mb-6 text-2xl font-semibold">Suvestinė</h1>

<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
	<Card.Root>
		<Card.Header class="pb-2"><Card.Description>Pajamos (šie metai)</Card.Description></Card.Header>
		<Card.Content class="text-2xl font-semibold">{fmtEur(taxes?.income_total ?? 0)}</Card.Content>
	</Card.Root>
	<Card.Root>
		<Card.Header class="pb-2"><Card.Description>Atskaitymai</Card.Description></Card.Header>
		<Card.Content class="text-2xl font-semibold"
			>{fmtEur(taxes?.deductions_applied ?? 0)}</Card.Content
		>
	</Card.Root>
	<Card.Root>
		<Card.Header class="pb-2"><Card.Description>Mokesčiai {year} m.</Card.Description></Card.Header>
		<Card.Content class="text-2xl font-semibold">{fmtEur(taxes?.total ?? 0)}</Card.Content>
	</Card.Root>
	<Card.Root>
		<Card.Header class="pb-2"><Card.Description>Šio mėn. pajamos − išlaidos</Card.Description></Card.Header>
		<Card.Content class="text-2xl font-semibold">{fmtEur(journal?.net ?? 0)}</Card.Content>
	</Card.Root>
</div>

<div class="mt-6 grid gap-4 lg:grid-cols-2">
	<Card.Root>
		<Card.Header><Card.Title>Neapmokėtos sąskaitos</Card.Title></Card.Header>
		<Card.Content>
			{#if unpaid.length === 0}
				<p class="text-sm text-muted-foreground">Nėra išrašytų neapmokėtų sąskaitų.</p>
			{:else}
				<ul class="divide-y">
					{#each unpaid as inv (inv.id)}
						<li class="flex items-center justify-between py-2 text-sm">
							<a
								href={resolve('/invoices/[id]', { id: String(inv.id) })}
								class="font-medium hover:underline">{inv.full_number}</a
							>
							<span class="text-muted-foreground">{inv.client.name}</span>
							<span class="flex items-center gap-2">
								<Badge variant="secondary">{STATUS_LABELS[inv.status]}</Badge>
								{fmtEur(inv.total)}
							</span>
						</li>
					{/each}
				</ul>
			{/if}
		</Card.Content>
	</Card.Root>
	<Card.Root>
		<Card.Header><Card.Title>Mokesčiai {year} m.</Card.Title></Card.Header>
		<Card.Content>
			{#if taxes}
				<ul class="space-y-2 text-sm">
					<li class="flex justify-between">
						<span>GPM ({taxes.gpm.note || 'tarifas'})</span><span>{fmtEur(taxes.gpm.amount)}</span>
					</li>
					<li class="flex justify-between">
						<span>VSD</span><span>{fmtEur(taxes.vsd.amount)}</span>
					</li>
					<li class="flex justify-between">
						<span>PSD</span><span>{fmtEur(taxes.psd.amount)}</span>
					</li>
					<li class="flex justify-between border-t pt-2 font-semibold">
						<span>Iš viso</span><span>{fmtEur(taxes.total)}</span>
					</li>
				</ul>
				{#each taxes.warnings as w (w)}
					<p class="mt-2 text-xs text-amber-600">{w}</p>
				{/each}
			{:else}
				<p class="text-sm text-muted-foreground">Kraunama…</p>
			{/if}
		</Card.Content>
	</Card.Root>
</div>
