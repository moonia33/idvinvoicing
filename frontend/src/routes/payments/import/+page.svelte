<script lang="ts">
	import { resolve } from '$app/paths';
	import { api } from '#lib/api';
	import { auth } from '#lib/auth.svelte';
	import type { ImportEntry, ImportResult } from '#lib/types';
	import { fmtDate, fmtMoney, PAYMENT_METHODS } from '#lib/format';
	import { Button } from '#lib/components/ui/button';
	import { Badge } from '#lib/components/ui/badge';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import * as Table from '#lib/components/ui/table';
	import { cn } from '#lib/utils.js';

	let file = $state<File | null>(null);
	let preview = $state<ImportResult | null>(null);
	let result = $state<ImportResult | null>(null);
	let ignored = $state<Record<string, boolean>>({});
	let showDuplicates = $state(false);
	let busy = $state(false);
	let error = $state('');
	let previewTenant = $state<number | null>(null);

	// Perjungus veiklą senos peržiūros nebegalima importuoti.
	$effect(() => {
		if (preview && auth.currentTenant?.id !== previewTenant) {
			preview = null;
			error = 'Pasikeitė aktyvi veikla – įkelkite išrašą iš naujo';
		}
	});

	const key = (e: ImportEntry) => `${e.account_iban}:${e.external_id}`;
	let importable = $derived(
		preview ? preview.entries.filter((e) => !e.duplicate && e.supported) : []
	);
	let shown = $derived(
		preview ? preview.entries.filter((e) => showDuplicates || (!e.duplicate && e.supported)) : []
	);
	let ignoredCount = $derived(importable.filter((e) => ignored[key(e)]).length);
	let allIgnored = $derived(importable.length > 0 && ignoredCount === importable.length);

	function form(commit: boolean): FormData {
		const fd = new FormData();
		fd.append('file', file as File);
		if (commit) {
			fd.append('commit', 'true');
			fd.append('tenant_id', String(previewTenant));
			fd.append('ignored', JSON.stringify(Object.keys(ignored).filter((k) => ignored[k])));
		}
		return fd;
	}

	async function onFile(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		file = input.files?.[0] ?? null;
		preview = null;
		result = null;
		error = '';
		if (!file) return;
		busy = true;
		try {
			previewTenant = auth.currentTenant?.id ?? null;
			preview = await api<ImportResult>('/transfers/import', { method: 'POST', body: form(false) });
			ignored = Object.fromEntries(preview.entries.map((x) => [key(x), x.own_transfer]));
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		} finally {
			busy = false;
		}
	}

	function toggleAll() {
		const value = !allIgnored;
		ignored = Object.fromEntries(importable.map((x) => [key(x), value]));
	}

	async function commit() {
		busy = true;
		error = '';
		try {
			result = await api<ImportResult>('/transfers/import', { method: 'POST', body: form(true) });
			preview = null;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		} finally {
			busy = false;
		}
	}
</script>

<div class="mb-6 flex items-center gap-3">
	<Button variant="ghost" href={resolve('/payments')}>← Atgal</Button>
	<h1 class="text-2xl font-semibold">Banko išrašo importas</h1>
</div>

<div class="mx-auto max-w-6xl space-y-4">
	<Card.Root>
		<Card.Content class="space-y-3 pt-6">
			<Label for="file">Išrašas ISO 20022 camt.053 XML formatu</Label>
			<input
				id="file"
				type="file"
				accept=".xml,application/xml,text/xml"
				class="block w-full text-sm file:mr-3 file:rounded-md file:border file:bg-background file:px-3 file:py-1.5 file:text-sm"
				onchange={onFile}
				disabled={busy}
			/>
			<p class="text-sm text-muted-foreground">
				Interneto banke pasirinkite sąskaitos išrašą XML (camt.053) formatu: Citadele, Paysera,
				Swedbank, SEB, Luminor ir kt. Tą patį išrašą galima įkelti pakartotinai – jau importuotos
				operacijos praleidžiamos.
			</p>
			{#if busy && !preview}<p class="text-sm text-muted-foreground">Skaitoma…</p>{/if}
			{#if error}<p class="text-sm text-destructive">{error}</p>{/if}
		</Card.Content>
	</Card.Root>

	{#if result}
		<Card.Root>
			<Card.Content class="space-y-3 pt-6">
				<p class="font-medium">
					Importuota operacijų: {result.created_count}. Praleista jau buvusių: {result.duplicate_count}.
					{#if result.auto_allocated_count}
						Automatiškai sudengta pagal sąskaitos numerį: {result.auto_allocated_count}.
					{/if}
				</p>
				<p class="text-sm text-muted-foreground">
					Naujos operacijos yra „Nesudengtos“. Atidarykite jas ir sudenkite su sąskaitomis arba
					pirkimais.
				</p>
				<div class="flex flex-wrap gap-2">
					<Button href={resolve('/payments/reconcile')}>Sutikrinti nesudengtus</Button>
					<Button variant="outline" href={resolve('/payments') + '?tab=open'}
						>Visi nesudengti</Button
					>
				</div>
			</Card.Content>
		</Card.Root>
	{/if}

	{#if preview}
		<Card.Root>
			<Card.Header>
				<Card.Title class="text-base">Peržiūra</Card.Title>
				<Card.Description>
					{#each preview.statements as s (s.account_iban + s.currency)}
						<span class="block">
							{s.bank_name || 'Bankas'} · {s.account_iban} · {s.currency} · {fmtDate(s.period_from)} –
							{fmtDate(s.period_to)} · operacijų: {s.entries}{s.skipped
								? ` (neįvykdytų praleista: ${s.skipped})`
								: ''}
						</span>
					{/each}
				</Card.Description>
			</Card.Header>
			<Card.Content class="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
				<span>Naujų: <b>{preview.new_count}</b></span>
				<span>Jau importuotų: <b>{preview.duplicate_count}</b></span>
				{#if preview.unsupported_count}
					<span class="text-destructive">
						Nepalaikoma valiuta: <b>{preview.unsupported_count}</b>
					</span>
				{/if}
				<span>Bus pažymėta „Neapskaitoma“: <b>{ignoredCount}</b></span>
				<label class="ml-auto flex items-center gap-2">
					<input type="checkbox" class="size-4" bind:checked={showDuplicates} />
					Rodyti jau importuotas
				</label>
			</Card.Content>
			<Table.Root>
				<Table.Header>
					<Table.Row>
						<Table.Head>Data</Table.Head>
						<Table.Head>Kontragentas</Table.Head>
						<Table.Head>Paskirtis</Table.Head>
						<Table.Head>Būdas</Table.Head>
						<Table.Head class="text-right">Suma</Table.Head>
						<Table.Head class="text-center">
							<button
								type="button"
								class="underline-offset-2 hover:underline"
								title="Pažymėti visas / nuimti"
								onclick={toggleAll}>Neapskaitoma</button
							>
						</Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					{#each shown as e (key(e))}
						<Table.Row class={cn((e.duplicate || !e.supported) && 'opacity-50')}>
							<Table.Cell class="whitespace-nowrap">{fmtDate(e.date)}</Table.Cell>
							<Table.Cell>
								<span class="font-medium">{e.counterparty_name || '–'}</span>
								{#if e.counterparty_id}<Badge variant="secondary" class="ml-1">Kontaktas</Badge
									>{/if}
								{#if e.own_transfer}<Badge variant="outline" class="ml-1">Sava sąskaita</Badge>{/if}
								{#if e.duplicate}<Badge variant="outline" class="ml-1">Jau yra</Badge>{/if}
								{#if e.counterparty_iban}
									<span class="block text-xs text-muted-foreground">{e.counterparty_iban}</span>
								{/if}
							</Table.Cell>
							<Table.Cell class="max-w-sm text-sm text-muted-foreground">
								<span class="line-clamp-2">{e.reference}</span>
							</Table.Cell>
							<Table.Cell class="text-sm">{PAYMENT_METHODS[e.method]}</Table.Cell>
							<Table.Cell
								class={cn(
									'text-right whitespace-nowrap tabular-nums',
									e.direction === 'in' ? 'text-emerald-700' : ''
								)}
							>
								{e.direction === 'in' ? '+' : '−'}{fmtMoney(e.amount, e.currency)}
							</Table.Cell>
							<Table.Cell class="text-center">
								{#if !e.duplicate && e.supported}
									<input
										type="checkbox"
										class="size-4"
										aria-label="Neapskaitoma"
										bind:checked={ignored[key(e)]}
									/>
								{/if}
							</Table.Cell>
						</Table.Row>
					{/each}
					{#if shown.length === 0}
						<Table.Row>
							<Table.Cell colspan={6} class="text-center text-muted-foreground">
								Naujų operacijų nėra – šis išrašas jau importuotas
							</Table.Cell>
						</Table.Row>
					{/if}
				</Table.Body>
			</Table.Root>
			<Card.Footer class="flex justify-end gap-3 pt-4">
				<Button type="button" disabled={busy || importable.length === 0} onclick={commit}>
					{busy ? 'Importuojama…' : `Importuoti ${importable.length} operacijas`}
				</Button>
			</Card.Footer>
		</Card.Root>
	{/if}
</div>
