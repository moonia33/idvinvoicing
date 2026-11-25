<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api';
	import type { Category, LedgerHint, Transfer, TransferSuggestions } from '#lib/types';
	import { fmtDate, fmtMoney, PAYMENT_METHODS } from '#lib/format';
	import { fromCents, toCents } from '#lib/allocate';
	import { Button } from '#lib/components/ui/button';
	import { Badge } from '#lib/components/ui/badge';
	import { Input } from '#lib/components/ui/input';
	import * as Card from '#lib/components/ui/card';
	import * as Select from '#lib/components/ui/select';
	import { cn } from '#lib/utils.js';

	const TAX_KINDS: Record<string, string> = {
		'': 'Ne mokestis',
		gpm: 'GPM',
		vsd: 'VSD',
		psd: 'PSD'
	};

	type LedgerForm = LedgerHint & { open: boolean; exchange_rate: string };

	let transfers = $state<Transfer[]>([]);
	let suggestions = $state<Record<number, TransferSuggestions>>({});
	let categories = $state<Category[]>([]);
	let forms = $state<Record<number, LedgerForm>>({});
	let busy = $state<number | null>(null);
	let errors = $state<Record<number, string>>({});
	let loading = $state(true);
	let done = $state(0);

	async function load() {
		loading = true;
		const [list, sug, cats] = await Promise.all([
			api<Transfer[]>('/transfers?status=open'),
			api<TransferSuggestions[]>('/transfers/suggestions'),
			api<Category[]>('/ledger/categories')
		]);
		transfers = list.filter((t) => !t.ignored && !t.ledger_entry_id);
		suggestions = Object.fromEntries(sug.map((s) => [s.transfer_id, s]));
		categories = cats;
		forms = {};
		loading = false;
	}

	function ledgerForm(t: Transfer): LedgerForm {
		const hint = suggestions[t.id]?.ledger;
		return {
			open: true,
			kind: t.direction === 'in' ? 'income' : 'expense',
			tax_kind: hint?.tax_kind ?? '',
			tax_year: hint?.tax_year ?? null,
			description: hint?.description ?? '',
			deductible: hint?.deductible ?? true,
			category_id: hint?.category_id ?? null,
			exchange_rate: ''
		};
	}

	async function act(t: Transfer, fn: () => Promise<unknown>) {
		busy = t.id;
		errors[t.id] = '';
		try {
			await fn();
			transfers = transfers.filter((x) => x.id !== t.id);
			done += 1;
		} catch (err) {
			errors[t.id] = err instanceof Error ? err.message : 'Klaida';
		} finally {
			busy = null;
		}
	}

	function allocate(t: Transfer, kind: string, id: number, remaining: string) {
		const amount = fromCents(Math.min(toCents(t.unallocated), toCents(remaining)));
		return act(t, () =>
			api(`/transfers/${t.id}/allocations`, {
				method: 'POST',
				body: { [kind === 'invoice' ? 'invoice_id' : 'purchase_id']: id, amount }
			})
		);
	}

	function toLedger(t: Transfer) {
		const f = forms[t.id];
		return act(t, () =>
			api(`/transfers/${t.id}/ledger`, {
				method: 'POST',
				body: {
					kind: f.kind,
					category_id: f.category_id,
					description: f.description,
					deductible: f.deductible,
					tax_kind: f.tax_kind,
					tax_year: f.tax_kind ? Number(f.tax_year) || null : null,
					exchange_rate: t.currency === 'EUR' ? null : f.exchange_rate || null
				}
			})
		);
	}

	function markIgnored(t: Transfer) {
		return act(t, () =>
			api(`/transfers/${t.id}`, {
				method: 'PUT',
				body: {
					date: t.date,
					amount: t.amount,
					method: t.method,
					counterparty_id: t.counterparty_id,
					counterparty_name: t.counterparty_name,
					counterparty_iban: t.counterparty_iban,
					reference: t.reference,
					note: t.note,
					doc_number: t.doc_number,
					ignored: true
				}
			})
		);
	}

	onMount(load);
</script>

<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
	<div class="flex items-center gap-3">
		<Button variant="ghost" href={resolve('/payments')}>← Atgal</Button>
		<h1 class="text-2xl font-semibold">Sutikrinimas</h1>
	</div>
	<div class="text-sm text-muted-foreground">
		Liko: <b>{transfers.length}</b>{#if done}&nbsp;· sutvarkyta: <b>{done}</b>{/if}
	</div>
</div>

{#if loading}
	<p class="text-muted-foreground">Kraunama…</p>
{:else if transfers.length === 0}
	<Card.Root>
		<Card.Content class="pt-6 text-center text-muted-foreground">
			Visi mokėjimai sudengti arba pažymėti. <a class="underline" href={resolve('/payments')}
				>Į mokėjimų sąrašą</a
			>
		</Card.Content>
	</Card.Root>
{:else}
	<div class="space-y-3">
		{#each transfers as t (t.id)}
			{@const s = suggestions[t.id]}
			<Card.Root class={cn(busy === t.id && 'opacity-60')}>
				<Card.Content class="grid gap-4 pt-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
					<div class="min-w-0 space-y-1">
						<div class="flex items-baseline justify-between gap-3">
							<a
								class="truncate font-medium hover:underline"
								href={resolve('/payments/[id]', { id: String(t.id) })}
								>{t.counterparty_display || 'Nenurodytas kontragentas'}</a
							>
							<span
								class={cn(
									'font-semibold whitespace-nowrap tabular-nums',
									t.direction === 'in' && 'text-emerald-700'
								)}
							>
								{t.direction === 'in' ? '+' : '−'}{fmtMoney(t.amount, t.currency)}
							</span>
						</div>
						<div class="text-sm text-muted-foreground">
							{fmtDate(t.date)} · {PAYMENT_METHODS[t.method]}
							{#if t.status === 'partial'}
								· nesudengta {fmtMoney(t.unallocated, t.currency)}{/if}
						</div>
						{#if t.reference}<p class="line-clamp-2 text-sm">{t.reference}</p>{/if}
					</div>

					<div class="space-y-2">
						{#each s?.documents ?? [] as d (d.kind + d.id)}
							<div
								class="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
							>
								<div class="min-w-0 text-sm">
									<span class="font-medium">{d.label}</span>
									<span class="text-muted-foreground"
										>· {d.counterparty_name} · likutis {fmtMoney(d.remaining, d.currency)}</span
									>
									<span class="mt-0.5 flex flex-wrap gap-1">
										{#each d.reasons as r (r)}<Badge variant="secondary">{r}</Badge>{/each}
									</span>
								</div>
								<Button
									size="sm"
									disabled={busy === t.id}
									onclick={() => allocate(t, d.kind, d.id, d.remaining)}>Sudengti</Button
								>
							</div>
						{/each}

						{#if forms[t.id]?.open}
							{@const f = forms[t.id]}
							<div class="grid gap-2 rounded-md border bg-muted/40 p-3 sm:grid-cols-2">
								<Input placeholder="Aprašymas" bind:value={f.description} maxlength={300} />
								<Select.Root
									type="single"
									value={f.category_id ? String(f.category_id) : ''}
									onValueChange={(v) => (f.category_id = v ? Number(v) : null)}
								>
									<Select.Trigger class="w-full">
										{categories.find((c) => c.id === f.category_id)?.name ?? 'Be kategorijos'}
									</Select.Trigger>
									<Select.Content>
										<Select.Item value="" label="Be kategorijos">Be kategorijos</Select.Item>
										{#each categories.filter((c) => c.kind === f.kind) as c (c.id)}
											<Select.Item value={String(c.id)} label={c.name}>{c.name}</Select.Item>
										{/each}
									</Select.Content>
								</Select.Root>
								{#if f.kind === 'expense'}
									<Select.Root type="single" bind:value={f.tax_kind}>
										<Select.Trigger class="w-full">{TAX_KINDS[f.tax_kind]}</Select.Trigger>
										<Select.Content>
											{#each Object.entries(TAX_KINDS) as [v, l] (v)}
												<Select.Item value={v} label={l}>{l}</Select.Item>
											{/each}
										</Select.Content>
									</Select.Root>
									{#if f.tax_kind}
										<Input
											type="number"
											min="2000"
											max="2100"
											placeholder="Už kuriuos metus"
											bind:value={f.tax_year}
										/>
									{/if}
								{/if}
								{#if t.currency !== 'EUR'}
									<Input
										type="number"
										step="0.000001"
										min="0"
										placeholder={`Kursas ${t.currency} → EUR`}
										bind:value={f.exchange_rate}
										required
									/>
								{/if}
								<label class="flex items-center gap-2 text-sm">
									<input type="checkbox" class="size-4" bind:checked={f.deductible} />
									Leidžiami atskaitymai
								</label>
								<div class="flex justify-end gap-2 sm:col-span-2">
									<Button variant="ghost" size="sm" onclick={() => (f.open = false)}
										>Atšaukti</Button
									>
									<Button size="sm" disabled={busy === t.id} onclick={() => toLedger(t)}
										>Įrašyti į žurnalą</Button
									>
								</div>
							</div>
						{/if}

						<div class="flex flex-wrap gap-2">
							{#if !forms[t.id]?.open && t.status === 'unallocated'}
								<Button variant="outline" size="sm" onclick={() => (forms[t.id] = ledgerForm(t))}>
									{#if s?.ledger}
										Žurnale: {s.ledger.tax_kind
											? `${s.ledger.tax_kind.toUpperCase()} ${s.ledger.tax_year ?? ''}`
											: s.ledger.description}
									{:else}
										Į žurnalą be dokumento
									{/if}
								</Button>
							{/if}
							{#if t.status === 'unallocated'}
								<Button variant="ghost" size="sm" onclick={() => markIgnored(t)}
									>Neapskaitoma</Button
								>
							{/if}
							{#if !s?.documents.length}
								<Button
									variant="ghost"
									size="sm"
									href={resolve('/payments/[id]', { id: String(t.id) })}>Ieškoti dokumento</Button
								>
							{/if}
						</div>
						{#if errors[t.id]}<p class="text-sm text-destructive">{errors[t.id]}</p>{/if}
					</div>
				</Card.Content>
			</Card.Root>
		{/each}
	</div>
{/if}
