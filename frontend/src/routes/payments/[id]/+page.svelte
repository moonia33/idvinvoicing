<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { api } from '#lib/api';
	import type { Contact, OpenDocument, PaymentMethod, Transfer } from '#lib/types';
	import {
		fmtMoney,
		fmtDate,
		PAYMENT_METHODS,
		TRANSFER_DIRECTIONS,
		TRANSFER_STATUS_LABELS,
		TRANSFER_STATUS_VARIANTS
	} from '#lib/format';
	import { fromCents, queryString, toCents } from '#lib/allocate';
	import { Button } from '#lib/components/ui/button';
	import { Badge } from '#lib/components/ui/badge';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import * as Select from '#lib/components/ui/select';
	import * as Table from '#lib/components/ui/table';
	import { Trash2 } from '@lucide/svelte';

	const id = page.params.id;
	let t = $state<Transfer | null>(null);
	let contacts = $state<Contact[]>([]);
	let docs = $state<OpenDocument[]>([]);
	let amounts = $state<Record<string, string>>({});
	let allDocs = $state(false);
	let form = $state({
		date: '',
		amount: '',
		method: 'bank' as PaymentMethod,
		counterparty_id: '',
		counterparty_name: '',
		counterparty_iban: '',
		reference: '',
		note: '',
		ignored: false
	});
	let error = $state('');
	let saved = $state(false);

	const key = (d: OpenDocument) => `${d.kind}-${d.id}`;

	function fill(x: Transfer) {
		t = x;
		form = {
			date: x.date,
			amount: x.amount,
			method: x.method,
			counterparty_id: x.counterparty_id ? String(x.counterparty_id) : '',
			counterparty_name: x.counterparty_name,
			counterparty_iban: x.counterparty_iban,
			reference: x.reference,
			note: x.note,
			ignored: x.ignored
		};
	}

	async function loadDocs() {
		if (!t || t.ignored || toCents(t.unallocated) <= 0) {
			docs = [];
			return;
		}
		const qs = queryString({
			direction: t.direction,
			counterparty_id: allDocs ? '' : t.counterparty_id
		});
		const list = await api<OpenDocument[]>(`/transfers/open-documents${qs}`);
		docs = list.filter((d) => d.currency === t!.currency);
		const left = toCents(t.unallocated);
		amounts = Object.fromEntries(
			docs.map((d) => [key(d), fromCents(Math.min(left, toCents(d.remaining)))])
		);
	}

	async function load() {
		fill(await api<Transfer>(`/transfers/${id}`));
		await loadDocs();
	}

	async function run(fn: () => Promise<Transfer | void>) {
		error = '';
		saved = false;
		try {
			const res = await fn();
			if (res) fill(res);
			await loadDocs();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		}
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		await run(() =>
			api<Transfer>(`/transfers/${id}`, {
				method: 'PUT',
				body: {
					...form,
					counterparty_id: form.counterparty_id ? Number(form.counterparty_id) : null
				}
			})
		);
		if (!error) saved = true;
	}

	const allocate = (d: OpenDocument) =>
		run(() =>
			api<Transfer>(`/transfers/${id}/allocations`, {
				method: 'POST',
				body: {
					[d.kind === 'invoice' ? 'invoice_id' : 'purchase_id']: d.id,
					amount: amounts[key(d)]
				}
			})
		);

	const unallocate = (kind: string, allocId: number) =>
		run(() =>
			api<Transfer>(`/transfers/${id}/allocations/${kind}/${allocId}`, { method: 'DELETE' })
		);

	async function remove() {
		if (!confirm('Ištrinti mokėjimą ir visus jo sudengimus?')) return;
		await api(`/transfers/${id}`, { method: 'DELETE' });
		goto(resolve('/payments'));
	}

	const docHref = (kind: string, docId: number) =>
		kind === 'invoice'
			? resolve('/invoices/[id]', { id: String(docId) })
			: resolve('/purchases/[id]', { id: String(docId) });

	onMount(async () => {
		await load();
		contacts = await api<Contact[]>(t?.direction === 'out' ? '/suppliers' : '/clients');
	});
</script>

<div class="mb-6 flex flex-wrap items-center gap-3">
	<Button variant="ghost" href={resolve('/payments')}>← Mokėjimai</Button>
	{#if t}
		<h1 class="text-2xl font-semibold">
			{TRANSFER_DIRECTIONS[t.direction]}
			{fmtMoney(t.amount, t.currency)}
		</h1>
		<Badge variant={TRANSFER_STATUS_VARIANTS[t.status]}>{TRANSFER_STATUS_LABELS[t.status]}</Badge>
		{#if t.source === 'import'}<Badge variant="outline">Banko išrašas</Badge>{/if}
		<Button variant="ghost" size="icon" class="ml-auto" title="Ištrinti" onclick={remove}>
			<Trash2 class="size-4" />
		</Button>
	{/if}
</div>

{#if t}
	<div class="grid gap-4 lg:grid-cols-5">
		<form onsubmit={save} class="lg:col-span-2">
			<Card.Root>
				<Card.Content class="space-y-4 pt-6">
					<div class="grid grid-cols-2 gap-3">
						<div class="space-y-1.5">
							<Label for="date">Data</Label>
							<Input id="date" type="date" bind:value={form.date} required />
						</div>
						<div class="space-y-1.5">
							<Label for="amount">Suma ({t.currency})</Label>
							<Input
								id="amount"
								type="number"
								step="0.01"
								min="0.01"
								bind:value={form.amount}
								disabled={t.source === 'import'}
								required
							/>
						</div>
					</div>
					<div class="space-y-1.5">
						<Label>Būdas</Label>
						<Select.Root type="single" bind:value={form.method}>
							<Select.Trigger class="w-full">{PAYMENT_METHODS[form.method]}</Select.Trigger>
							<Select.Content>
								{#each Object.entries(PAYMENT_METHODS) as [v, label] (v)}
									<Select.Item value={v} {label}>{label}</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					</div>
					<div class="space-y-1.5">
						<Label>Kontragentas</Label>
						<Select.Root type="single" bind:value={form.counterparty_id}>
							<Select.Trigger class="w-full">
								{contacts.find((c) => String(c.id) === form.counterparty_id)?.name ?? 'Nenurodyta'}
							</Select.Trigger>
							<Select.Content>
								<Select.Item value="" label="Nenurodyta">Nenurodyta</Select.Item>
								{#each contacts as c (c.id)}
									<Select.Item value={String(c.id)} label={c.name}>{c.name}</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					</div>
					<div class="grid grid-cols-2 gap-3">
						<div class="space-y-1.5">
							<Label for="cpname">Pavadinimas (banke)</Label>
							<Input id="cpname" bind:value={form.counterparty_name} />
						</div>
						<div class="space-y-1.5">
							<Label for="iban">IBAN</Label>
							<Input id="iban" bind:value={form.counterparty_iban} maxlength={34} />
						</div>
					</div>
					<div class="space-y-1.5">
						<Label for="reference">Mokėjimo paskirtis</Label>
						<Input id="reference" bind:value={form.reference} maxlength={500} />
					</div>
					<div class="space-y-1.5">
						<Label for="note">Pastaba</Label>
						<Input id="note" bind:value={form.note} maxlength={200} />
					</div>
					<label class="flex items-center gap-2 text-sm">
						<input
							type="checkbox"
							class="size-4"
							bind:checked={form.ignored}
							disabled={t.allocations.length > 0}
						/>
						Neapskaitoma (asmeninė operacija)
					</label>
					<div class="flex items-center justify-end gap-3">
						{#if saved}<span class="text-sm text-muted-foreground">Išsaugota</span>{/if}
						<Button type="submit">Išsaugoti</Button>
					</div>
				</Card.Content>
			</Card.Root>
		</form>

		<div class="space-y-4 lg:col-span-3">
			{#if error}<p class="text-sm text-destructive">{error}</p>{/if}
			<Card.Root>
				<Card.Header>
					<Card.Title class="text-base">Sudengta</Card.Title>
					<Card.Description>
						{fmtMoney(t.allocated_total, t.currency)} iš {fmtMoney(t.amount, t.currency)}, liko
						{fmtMoney(t.unallocated, t.currency)}
					</Card.Description>
				</Card.Header>
				<Table.Root>
					<Table.Body>
						{#each t.allocations as a (`${a.kind}-${a.id}`)}
							<Table.Row>
								<Table.Cell class="font-medium">
									<a class="hover:underline" href={docHref(a.kind, a.document_id)}
										>{a.document_label}</a
									>
									{#if a.doc_number}
										<span class="text-xs text-muted-foreground">({a.doc_number})</span>
									{/if}
								</Table.Cell>
								<Table.Cell class="text-right tabular-nums">
									{fmtMoney(a.amount, t.currency)}
								</Table.Cell>
								<Table.Cell class="w-10">
									<Button
										variant="ghost"
										size="icon"
										title="Panaikinti sudengimą"
										onclick={() => unallocate(a.kind, a.id)}
									>
										<Trash2 class="size-4" />
									</Button>
								</Table.Cell>
							</Table.Row>
						{/each}
						{#if t.allocations.length === 0}
							<Table.Row>
								<Table.Cell class="text-center text-muted-foreground">Nesudengta</Table.Cell>
							</Table.Row>
						{/if}
					</Table.Body>
				</Table.Root>
			</Card.Root>

			{#if !t.ignored && toCents(t.unallocated) > 0}
				<Card.Root>
					<Card.Header>
						<Card.Title class="text-base">
							Neapmokėti {t.direction === 'in' ? 'sąskaitos' : 'pirkimai'}
						</Card.Title>
						{#if t.counterparty_id}
							<Card.Action>
								<label class="flex items-center gap-2 text-sm">
									<input
										type="checkbox"
										class="size-4"
										bind:checked={allDocs}
										onchange={loadDocs}
									/>
									Visų kontragentų
								</label>
							</Card.Action>
						{/if}
					</Card.Header>
					<Table.Root>
						<Table.Body>
							{#each docs as d (key(d))}
								<Table.Row>
									<Table.Cell class="font-medium">{d.label}</Table.Cell>
									<Table.Cell>{d.counterparty_name}</Table.Cell>
									<Table.Cell class="whitespace-nowrap">{fmtDate(d.date)}</Table.Cell>
									<Table.Cell class="text-right tabular-nums">
										{fmtMoney(d.remaining, d.currency)}
									</Table.Cell>
									<Table.Cell class="w-32">
										<Input
											type="number"
											step="0.01"
											min="0.01"
											class="text-right"
											aria-label={`Suma ${d.label}`}
											bind:value={amounts[key(d)]}
										/>
									</Table.Cell>
									<Table.Cell class="w-24">
										<Button size="sm" onclick={() => allocate(d)}>Sudengti</Button>
									</Table.Cell>
								</Table.Row>
							{/each}
							{#if docs.length === 0}
								<Table.Row>
									<Table.Cell class="text-center text-muted-foreground">
										Neapmokėtų dokumentų nėra
									</Table.Cell>
								</Table.Row>
							{/if}
						</Table.Body>
					</Table.Root>
				</Card.Root>
			{/if}
		</div>
	</div>
{/if}
