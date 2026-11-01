<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api } from '#lib/api';
	import type { Category, PaymentMethod, Purchase, PurchaseDocType } from '#lib/types';
	import {
		fmtEur,
		fmtDate,
		PURCHASE_STATUS_LABELS,
		PURCHASE_DOC_TYPES,
		PURCHASE_DOC_KINDS,
		PAYMENT_METHODS
	} from '#lib/format';
	import { Button } from '#lib/components/ui/button';
	import { Badge } from '#lib/components/ui/badge';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import * as Table from '#lib/components/ui/table';
	import * as Dialog from '#lib/components/ui/dialog';
	import * as Select from '#lib/components/ui/select';
	import { XCircle, Coins, FileText, Pencil, Trash2, Plus } from '@lucide/svelte';

	let purchase = $state<Purchase | null>(null);
	let categories = $state<Category[]>([]);
	let error = $state('');

	let payOpen = $state(false);
	let payForm = $state({
		amount_original: '',
		exchange_rate: '',
		paid_at: new Date().toISOString().slice(0, 10),
		method: 'bank' as PaymentMethod,
		doc_type: 'kio' as PurchaseDocType,
		doc_number: '',
		note: ''
	});

	const id = $derived(page.params.id);

	async function load() {
		[purchase, categories] = await Promise.all([
			api<Purchase>(`/purchases/${id}`),
			api<Category[]>('/ledger/categories?kind=expense')
		]);
	}

	onMount(load);

	let payEditId = $state<number | null>(null);

	function openPay(p?: Purchase['payments'][number]) {
		if (p) {
			payEditId = p.id ?? null;
			payForm = {
				amount_original: p.amount_original,
				exchange_rate: p.exchange_rate,
				paid_at: p.paid_at,
				method: p.method,
				doc_type: p.doc_type || ('kio' as PurchaseDocType),
				doc_number: p.doc_number,
				note: p.note
			};
		} else {
			payEditId = null;
			payForm = {
				...payForm,
				amount_original: String(
					Math.max(Number(purchase?.total ?? 0) - Number(purchase?.paid_total ?? 0), 0).toFixed(2)
				),
				exchange_rate: purchase?.exchange_rate ?? '1'
			};
		}
		payOpen = true;
	}

	async function deletePayment(p: { id?: number }) {
		if (!p.id || !confirm('Ištrinti mokėjimą?')) return;
		await api(`/purchase-payments/${p.id}`, { method: 'DELETE' });
		await load();
	}

	let editOpen = $state(false);
	let editForm = $state({
		doc_type: 'sf' as Purchase['doc_type'],
		doc_number: '',
		document_date: '',
		due_date: '',
		notes: '',
		lines: [] as Purchase['lines']
	});

	function openEdit() {
		if (!purchase) return;
		editForm = {
			doc_type: purchase.doc_type,
			doc_number: purchase.doc_number,
			document_date: purchase.document_date,
			due_date: purchase.due_date ?? '',
			notes: purchase.notes,
			lines: purchase.lines.map((l) => ({ ...l }))
		};
		editOpen = true;
	}

	async function saveEdit(e: SubmitEvent) {
		e.preventDefault();
		if (!purchase) return;
		try {
			purchase = await api<Purchase>(`/purchases/${id}`, {
				method: 'PUT',
				body: {
					supplier_id: purchase.supplier.id,
					doc_type: editForm.doc_type,
					doc_number: editForm.doc_number,
					document_date: editForm.document_date,
					due_date: editForm.due_date || null,
					notes: editForm.notes,
					currency: purchase.currency,
					exchange_rate: purchase.exchange_rate,
					category_id: purchase.category_id,
					deductible: purchase.deductible,
					lines: editForm.lines
				}
			});
			editOpen = false;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		}
	}

	let payEur = $derived(
		(Number(payForm.amount_original) || 0) * (Number(payForm.exchange_rate) || 0)
	);

	async function addPayment(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		const body = {
			...payForm,
			exchange_rate: payForm.exchange_rate || null,
			doc_type: payForm.method === 'cash' ? payForm.doc_type : ''
		};
		try {
			if (payEditId) {
				await api(`/purchase-payments/${payEditId}`, { method: 'PUT', body });
			} else {
				await api(`/purchases/${id}/payments`, { method: 'POST', body });
			}
			payOpen = false;
			await load();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		}
	}

	async function cancel() {
		if (
			!confirm(
				purchase?.payments.length
					? 'Anuliuoti pirkinį? Visi mokėjimai bus ištrinti.'
					: 'Anuliuoti pirkinį?'
			)
		)
			return;
		try {
			purchase = await api<Purchase>(`/purchases/${id}/cancel`, { method: 'POST' });
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		}
	}
</script>

{#if purchase}
	<div class="mb-6 flex flex-wrap items-center gap-3">
		<Button variant="ghost" href="/purchases">← Atgal</Button>
		<h1 class="text-2xl font-semibold">
			{PURCHASE_DOC_KINDS[purchase.doc_type]}
			{purchase.doc_number || `#${purchase.id}`}
		</h1>
		<Badge>{PURCHASE_STATUS_LABELS[purchase.status]}</Badge>
		<div class="ml-auto flex gap-2">
			{#if purchase.status !== 'cancelled'}
				<Button variant="outline" onclick={openEdit}><Pencil class="size-4" /> Redaguoti</Button>
				<Button variant="outline" onclick={() => openPay()}
					><Coins class="size-4" /> Mokėjimas</Button
				>
				<Button variant="destructive" onclick={cancel}><XCircle class="size-4" /> Anuliuoti</Button>
			{/if}
		</div>
	</div>

	{#if error}<p class="mb-4 text-sm text-destructive">{error}</p>{/if}

	<div class="grid gap-4 lg:grid-cols-3">
		<Card.Root class="lg:col-span-2">
			<Card.Header><Card.Title>Dokumentas</Card.Title></Card.Header>
			<Card.Content>
				<dl class="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
					<div>
						<dt class="text-muted-foreground">Tiekėjas</dt>
						<dd class="font-medium">{purchase.supplier.name}</dd>
					</div>
					<div>
						<dt class="text-muted-foreground">Dok. nr.</dt>
						<dd>{purchase.doc_number || '–'}</dd>
					</div>
					<div>
						<dt class="text-muted-foreground">Dokumento data</dt>
						<dd>{fmtDate(purchase.document_date)}</dd>
					</div>
					<div>
						<dt class="text-muted-foreground">Apmokėti iki</dt>
						<dd>{fmtDate(purchase.due_date)}</dd>
					</div>
					<div>
						<dt class="text-muted-foreground">Valiuta / kursas</dt>
						<dd>
							{purchase.currency}{#if purchase.currency !== 'EUR'}
								· {purchase.exchange_rate}{/if}
						</dd>
					</div>
					<div>
						<dt class="text-muted-foreground">Kategorija</dt>
						<dd>
							{categories.find((c) => c.id === purchase?.category_id)?.name ?? '–'}
							{#if !purchase.deductible}<span class="text-muted-foreground">(neatskaitoma)</span
								>{/if}
						</dd>
					</div>
				</dl>
				<Table.Root class="mt-4">
					<Table.Header>
						<Table.Row>
							<Table.Head>Aprašymas</Table.Head>
							<Table.Head class="w-20">Kiekis</Table.Head>
							<Table.Head class="w-20">Vnt.</Table.Head>
							<Table.Head class="w-24 text-right">Kaina</Table.Head>
							<Table.Head class="w-24 text-right">Suma</Table.Head>
						</Table.Row>
					</Table.Header>
					<Table.Body>
						{#each purchase.lines as l (l.id)}
							<Table.Row>
								<Table.Cell>{l.description}</Table.Cell>
								<Table.Cell>{l.quantity}</Table.Cell>
								<Table.Cell>{l.unit}</Table.Cell>
								<Table.Cell class="text-right">{l.unit_price}</Table.Cell>
								<Table.Cell class="text-right">{l.total}</Table.Cell>
							</Table.Row>
						{/each}
						<Table.Row class="font-semibold">
							<Table.Cell colspan={4} class="text-right">Iš viso ({purchase.currency})</Table.Cell>
							<Table.Cell class="text-right">{purchase.total}</Table.Cell>
						</Table.Row>
						{#if purchase.currency !== 'EUR'}
							<Table.Row>
								<Table.Cell colspan={4} class="text-right">EUR</Table.Cell>
								<Table.Cell class="text-right">{fmtEur(purchase.total_eur)}</Table.Cell>
							</Table.Row>
						{/if}
					</Table.Body>
				</Table.Root>
				{#if purchase.notes}<p class="mt-3 text-sm text-muted-foreground">{purchase.notes}</p>{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header><Card.Title>Mokėjimai</Card.Title></Card.Header>
			<Card.Content>
				{#if purchase.payments.length === 0}
					<p class="text-sm text-muted-foreground">Mokėjimų nėra.</p>
				{:else}
					<ul class="space-y-2 text-sm">
						{#each purchase.payments as p (p.id)}
							<li class="border-b pb-2 last:border-0">
								<div class="flex items-center justify-between">
									<span>{p.paid_at}</span>
									<span class="font-medium">
										{fmtEur(p.amount_eur ?? 0)}{#if purchase.currency !== 'EUR'}
											<span class="text-xs text-muted-foreground">
												({p.amount_original} {purchase.currency})</span
											>{/if}
									</span>
								</div>
								<div class="mt-0.5 flex items-center justify-between text-xs text-muted-foreground">
									<span>{PAYMENT_METHODS[p.method]}{p.doc_number ? ` · ${p.doc_number}` : ''}</span>
									<span class="flex items-center gap-1">
										{#if p.doc_type === 'kio'}
											<Button
												variant="ghost"
												size="sm"
												class="h-6 px-1 text-xs"
												href="/api/v1/purchase-payments/{p.id}/kio.pdf"
												target="_blank"
											>
												<FileText class="size-3" />
												KIO
											</Button>
										{:else if p.doc_type === 'ppk'}
											<span>PPK</span>
										{/if}
										{#if purchase.status !== 'cancelled'}
											<Button variant="ghost" size="icon" class="h-6 w-6" onclick={() => openPay(p)}
												><Pencil class="size-3" /></Button
											>
											<Button
												variant="ghost"
												size="icon"
												class="h-6 w-6 text-destructive"
												onclick={() => deletePayment(p)}><Trash2 class="size-3" /></Button
											>
										{/if}
									</span>
								</div>
							</li>
						{/each}
					</ul>
				{/if}
				<div class="mt-4 space-y-1 border-t pt-3 text-sm">
					<div class="flex justify-between">
						<span>Suma</span><span>{purchase.total} {purchase.currency}</span>
					</div>
					<div class="flex justify-between">
						<span>Apmokėta</span><span>{purchase.paid_total} {purchase.currency}</span>
					</div>
					<div class="flex justify-between font-semibold">
						<span>Likutis</span>
						<span
							>{(Number(purchase.total) - Number(purchase.paid_total)).toFixed(2)}
							{purchase.currency}</span
						>
					</div>
				</div>
			</Card.Content>
		</Card.Root>
	</div>
{:else}
	<p class="text-muted-foreground">Kraunama…</p>
{/if}

<Dialog.Root bind:open={payOpen}>
	<Dialog.Content>
		<Dialog.Header><Dialog.Title>Registruoti mokėjimą</Dialog.Title></Dialog.Header>
		<form onsubmit={addPayment} class="space-y-3">
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5">
					<Label>Suma {purchase?.currency ?? ''} *</Label>
					<Input
						type="number"
						step="0.01"
						min="0.01"
						bind:value={payForm.amount_original}
						required
					/>
				</div>
				<div class="space-y-1.5">
					<Label>Data *</Label><Input type="date" bind:value={payForm.paid_at} required />
				</div>
			</div>
			{#if purchase && purchase.currency !== 'EUR'}
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1.5">
						<Label>Kursas → EUR</Label>
						<Input type="number" step="0.000001" min="0" bind:value={payForm.exchange_rate} />
					</div>
					<div class="space-y-1.5">
						<Label>EUR ekvivalentas</Label>
						<div class="rounded-md border px-3 py-2 text-sm">{payEur.toFixed(2)} €</div>
					</div>
				</div>
			{/if}
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5">
					<Label>Mokėjimo būdas</Label>
					<Select.Root type="single" bind:value={payForm.method}>
						<Select.Trigger class="w-full">{PAYMENT_METHODS[payForm.method]}</Select.Trigger>
						<Select.Content>
							{#each Object.entries(PAYMENT_METHODS) as [v, label] (v)}
								<Select.Item value={v} {label}>{label}</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-1.5">
					<Label>{payForm.method === 'cash' ? 'Kasos dokumentas' : 'Dokumento nr.'}</Label>
					{#if payForm.method === 'cash'}
						<Select.Root type="single" bind:value={payForm.doc_type}>
							<Select.Trigger class="w-full">{PURCHASE_DOC_TYPES[payForm.doc_type]}</Select.Trigger>
							<Select.Content>
								{#each Object.entries(PURCHASE_DOC_TYPES) as [v, label] (v)}
									<Select.Item value={v} {label}>{label}</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					{:else}
						<Input bind:value={payForm.doc_number} placeholder="Pvz. banko operacijos nr." />
					{/if}
				</div>
			</div>
			{#if payForm.method === 'cash'}
				<div class="space-y-1.5">
					<Label>Dokumento nr.</Label>
					<Input
						bind:value={payForm.doc_number}
						placeholder={payForm.doc_type === 'kio'
							? 'Tuščia – KIO numeris suteikiamas automatiškai'
							: 'Tiekėjo PPK numeris'}
					/>
				</div>
			{/if}
			<div class="space-y-1.5"><Label>Pastaba</Label><Input bind:value={payForm.note} /></div>
			<Dialog.Footer><Button type="submit">Išsaugoti</Button></Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={editOpen}>
	<Dialog.Content class="max-h-[90vh] overflow-y-auto sm:max-w-4xl">
		<Dialog.Header><Dialog.Title>Redaguoti pirkinį</Dialog.Title></Dialog.Header>
		<form onsubmit={saveEdit} class="space-y-3">
			<div class="grid grid-cols-4 gap-3">
				<div class="space-y-1.5">
					<Label>Dokumentas</Label>
					<Select.Root type="single" bind:value={editForm.doc_type}>
						<Select.Trigger class="w-full">{PURCHASE_DOC_KINDS[editForm.doc_type]}</Select.Trigger>
						<Select.Content>
							{#each Object.entries(PURCHASE_DOC_KINDS) as [v, label] (v)}
								<Select.Item value={v} {label}>{label}</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-1.5">
					<Label>Dok. nr.</Label><Input bind:value={editForm.doc_number} />
				</div>
				<div class="space-y-1.5">
					<Label>Dokumento data</Label><Input type="date" bind:value={editForm.document_date} />
				</div>
				<div class="space-y-1.5">
					<Label>Apmokėti iki</Label><Input type="date" bind:value={editForm.due_date} />
				</div>
			</div>
			<div class="space-y-2">
				{#each editForm.lines as line, i (i)}
					<div class="grid grid-cols-[1fr_70px_70px_100px_36px] gap-2">
						<Input bind:value={line.description} placeholder="Aprašymas" required />
						<Input type="number" step="0.001" min="0.001" bind:value={line.quantity} required />
						<Input bind:value={line.unit} />
						<Input type="number" step="0.01" min="0" bind:value={line.unit_price} required />
						<Button
							type="button"
							variant="ghost"
							size="icon"
							onclick={() => editForm.lines.splice(i, 1)}><Trash2 class="size-4" /></Button
						>
					</div>
				{/each}
				<Button
					type="button"
					variant="outline"
					size="sm"
					onclick={() =>
						editForm.lines.push({
							description: '',
							quantity: '1',
							unit: 'vnt.',
							unit_price: ''
						} as Purchase['lines'][number])}><Plus class="size-4" /> Eilutė</Button
				>
			</div>
			<div class="space-y-1.5"><Label>Pastabos</Label><Input bind:value={editForm.notes} /></div>
			<Dialog.Footer><Button type="submit">Išsaugoti pakeitimus</Button></Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
