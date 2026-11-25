<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { api } from '#lib/api';
	import type {
		Contact,
		OpenDocument,
		PaymentMethod,
		Transfer,
		TransferDirection
	} from '#lib/types';
	import {
		fmtMoney,
		fmtDate,
		CURRENCIES,
		PAYMENT_METHODS,
		DOC_TYPE_LABELS,
		PURCHASE_DOC_TYPES,
		TRANSFER_DIRECTIONS
	} from '#lib/format';
	import { autoAllocate, fromCents, queryString, toCents } from '#lib/allocate';
	import { Button } from '#lib/components/ui/button';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import * as Select from '#lib/components/ui/select';
	import * as Table from '#lib/components/ui/table';
	import { cn } from '#lib/utils.js';

	let direction = $state<TransferDirection>(
		page.url.searchParams.get('direction') === 'out' ? 'out' : 'in'
	);
	let date = $state(new Date().toISOString().slice(0, 10));
	let amount = $state('');
	let currency = $state<'EUR' | 'PLN'>('EUR');
	let method = $state<PaymentMethod>('bank');
	let counterpartyId = $state('');
	let counterpartyName = $state('');
	let reference = $state('');
	let note = $state('');
	let ignored = $state(false);
	let docType = $state('');

	let contacts = $state<Contact[]>([]);
	let docs = $state<OpenDocument[]>([]);
	let alloc = $state<Record<string, string>>({});
	let manual = $state(false);
	let error = $state('');
	let saving = $state(false);

	const key = (d: OpenDocument) => `${d.kind}-${d.id}`;
	let visibleDocs = $derived(docs.filter((d) => d.currency === currency));
	let allocatedCents = $derived(visibleDocs.reduce((s, d) => s + toCents(alloc[key(d)] ?? ''), 0));
	let leftCents = $derived(toCents(amount) - allocatedCents);
	let cashDocs = $derived(direction === 'in' ? DOC_TYPE_LABELS : PURCHASE_DOC_TYPES);

	async function loadContacts() {
		contacts = await api<Contact[]>(direction === 'in' ? '/clients' : '/suppliers');
	}

	async function loadDocs() {
		const qs = queryString({ direction, counterparty_id: counterpartyId });
		docs = await api<OpenDocument[]>(`/transfers/open-documents${qs}`);
		manual = false;
		redistribute();
	}

	function redistribute() {
		const amounts = autoAllocate(
			amount,
			visibleDocs.map((d) => d.remaining)
		);
		const next: Record<string, string> = {};
		visibleDocs.forEach((d, i) => (next[key(d)] = amounts[i]));
		alloc = next;
	}

	function onAmountInput() {
		if (!manual && !ignored) redistribute();
	}

	function setDirection(d: TransferDirection) {
		direction = d;
		counterpartyId = '';
		docType = '';
		loadContacts();
		loadDocs();
	}

	function pickCounterparty(v: string | undefined) {
		counterpartyId = v ?? '';
		loadDocs();
	}

	function payInFull(d: OpenDocument) {
		manual = true;
		if (!amount) amount = d.remaining;
		alloc[key(d)] = fromCents(
			Math.min(toCents(d.remaining), leftCents + toCents(alloc[key(d)] ?? ''))
		);
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		if (leftCents < 0) {
			error = 'Sudengiama suma viršija mokėjimo sumą';
			return;
		}
		saving = true;
		try {
			const allocations = ignored
				? []
				: visibleDocs
						.filter((d) => toCents(alloc[key(d)] ?? '') > 0)
						.map((d) => ({
							[d.kind === 'invoice' ? 'invoice_id' : 'purchase_id']: d.id,
							amount: alloc[key(d)]
						}));
			const t = await api<Transfer>('/transfers', {
				method: 'POST',
				body: {
					direction,
					date,
					amount,
					currency,
					method,
					counterparty_id: counterpartyId ? Number(counterpartyId) : null,
					counterparty_name: counterpartyId ? '' : counterpartyName,
					reference,
					note,
					ignored,
					doc_type: method === 'cash' ? docType : '',
					allocations
				}
			});
			goto(resolve('/payments/[id]', { id: String(t.id) }));
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
			saving = false;
		}
	}

	onMount(() => {
		loadContacts();
		loadDocs();
	});
</script>

<div class="mb-6 flex items-center gap-3">
	<Button variant="ghost" href={resolve('/payments')}>← Atgal</Button>
	<h1 class="text-2xl font-semibold">Naujas mokėjimas</h1>
</div>

<form onsubmit={save} class="mx-auto max-w-4xl space-y-4">
	<Card.Root>
		<Card.Content class="space-y-5 pt-6">
			<div class="inline-flex rounded-md border p-0.5" role="tablist">
				{#each Object.entries(TRANSFER_DIRECTIONS) as [v, label] (v)}
					<button
						type="button"
						role="tab"
						aria-selected={direction === v}
						class={cn(
							'rounded px-4 py-1.5 text-sm transition-colors',
							direction === v ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
						)}
						onclick={() => setDirection(v as TransferDirection)}>{label}</button
					>
				{/each}
			</div>

			<div class="grid gap-4 sm:grid-cols-4">
				<div class="space-y-1.5">
					<Label for="amount">Suma *</Label>
					<Input
						id="amount"
						type="number"
						step="0.01"
						min="0.01"
						inputmode="decimal"
						bind:value={amount}
						oninput={onAmountInput}
						required
					/>
				</div>
				<div class="space-y-1.5">
					<Label>Valiuta</Label>
					<Select.Root
						type="single"
						bind:value={currency}
						onValueChange={() => {
							manual = false;
							redistribute();
						}}
					>
						<Select.Trigger class="w-full">{currency}</Select.Trigger>
						<Select.Content>
							{#each CURRENCIES as c (c)}
								<Select.Item value={c} label={c}>{c}</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-1.5">
					<Label for="date">Data *</Label>
					<Input id="date" type="date" bind:value={date} required />
				</div>
				<div class="space-y-1.5">
					<Label>Būdas</Label>
					<Select.Root type="single" bind:value={method}>
						<Select.Trigger class="w-full">{PAYMENT_METHODS[method]}</Select.Trigger>
						<Select.Content>
							{#each Object.entries(PAYMENT_METHODS) as [v, label] (v)}
								<Select.Item value={v} {label}>{label}</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
			</div>

			<div class="grid gap-4 sm:grid-cols-2">
				<div class="space-y-1.5">
					<Label>{direction === 'in' ? 'Mokėtojas (klientas)' : 'Gavėjas (tiekėjas)'}</Label>
					<Select.Root type="single" value={counterpartyId} onValueChange={pickCounterparty}>
						<Select.Trigger class="w-full">
							{contacts.find((c) => String(c.id) === counterpartyId)?.name ?? 'Visi / nenurodyta'}
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="" label="Visi / nenurodyta">Visi / nenurodyta</Select.Item>
							{#each contacts as c (c.id)}
								<Select.Item value={String(c.id)} label={c.name}>{c.name}</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
				{#if !counterpartyId}
					<div class="space-y-1.5">
						<Label for="cpname">Kontragento pavadinimas</Label>
						<Input id="cpname" bind:value={counterpartyName} placeholder="Pvz. Sodra, VMI" />
					</div>
				{/if}
				<div class="space-y-1.5">
					<Label for="reference">Mokėjimo paskirtis</Label>
					<Input id="reference" bind:value={reference} maxlength={500} />
				</div>
				<div class="space-y-1.5">
					<Label for="note">Pastaba</Label>
					<Input id="note" bind:value={note} maxlength={200} />
				</div>
				{#if method === 'cash' && !ignored}
					<div class="space-y-1.5">
						<Label>Kasos dokumentas</Label>
						<Select.Root type="single" bind:value={docType}>
							<Select.Trigger class="w-full">{cashDocs[docType] ?? 'Be dokumento'}</Select.Trigger>
							<Select.Content>
								<Select.Item value="" label="Be dokumento">Be dokumento</Select.Item>
								{#each Object.entries(cashDocs) as [v, label] (v)}
									<Select.Item value={v} {label}>{label}</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					</div>
				{/if}
			</div>

			<label class="flex items-start gap-2 text-sm">
				<input type="checkbox" class="mt-0.5 size-4" bind:checked={ignored} />
				<span>
					<span class="font-medium">Neapskaitoma</span>
					<span class="block text-muted-foreground">
						Asmeninė operacija (pvz. pervedimas sau iš asmeninės sąskaitos) – nepatenka į veiklos
						apskaitą ir nesudengiama.
					</span>
				</span>
			</label>
		</Card.Content>
	</Card.Root>

	{#if !ignored}
		<Card.Root>
			<Card.Header>
				<Card.Title class="text-base">
					Sudengti su {direction === 'in' ? 'sąskaitomis' : 'pirkimais'}
				</Card.Title>
				<Card.Action>
					<Button
						variant="outline"
						size="sm"
						type="button"
						onclick={() => {
							manual = false;
							redistribute();
						}}>Paskirstyti nuo seniausio</Button
					>
				</Card.Action>
			</Card.Header>
			<Table.Root>
				<Table.Header>
					<Table.Row>
						<Table.Head>Dokumentas</Table.Head>
						<Table.Head>Kontragentas</Table.Head>
						<Table.Head>Data</Table.Head>
						<Table.Head>Apmokėti iki</Table.Head>
						<Table.Head class="text-right">Likutis</Table.Head>
						<Table.Head class="w-40 text-right">Sudengti</Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					{#each visibleDocs as d (key(d))}
						<Table.Row>
							<Table.Cell class="font-medium">
								<button
									type="button"
									class="underline-offset-2 hover:underline"
									title="Sudengti visą likutį"
									onclick={() => payInFull(d)}>{d.label}</button
								>
							</Table.Cell>
							<Table.Cell>{d.counterparty_name}</Table.Cell>
							<Table.Cell class="whitespace-nowrap">{fmtDate(d.date)}</Table.Cell>
							<Table.Cell class="whitespace-nowrap">{fmtDate(d.due_date)}</Table.Cell>
							<Table.Cell class="text-right tabular-nums">
								{fmtMoney(d.remaining, d.currency)}
							</Table.Cell>
							<Table.Cell class="text-right">
								<Input
									type="number"
									step="0.01"
									min="0"
									max={d.remaining}
									class="ml-auto w-32 text-right"
									aria-label={`Sudengti ${d.label}`}
									bind:value={alloc[key(d)]}
									oninput={() => (manual = true)}
								/>
							</Table.Cell>
						</Table.Row>
					{/each}
					{#if visibleDocs.length === 0}
						<Table.Row>
							<Table.Cell colspan={6} class="text-center text-muted-foreground">
								Neapmokėtų dokumentų nėra – mokėjimas liks nesudengtas (avansas)
							</Table.Cell>
						</Table.Row>
					{/if}
				</Table.Body>
			</Table.Root>
			<Card.Footer class="flex justify-end gap-6 pt-4 text-sm">
				<span
					>Sudengiama: <b class="tabular-nums">{fmtMoney(fromCents(allocatedCents), currency)}</b
					></span
				>
				<span class={cn(leftCents < 0 && 'text-destructive')}>
					{leftCents < 0 ? 'Viršyta' : 'Liks nesudengta'}:
					<b class="tabular-nums">{fmtMoney(fromCents(Math.abs(leftCents)), currency)}</b>
				</span>
			</Card.Footer>
		</Card.Root>
	{/if}

	{#if error}<p class="text-sm text-destructive">{error}</p>{/if}
	<div class="flex justify-end">
		<Button type="submit" disabled={saving}>{saving ? 'Saugoma…' : 'Išsaugoti mokėjimą'}</Button>
	</div>
</form>
