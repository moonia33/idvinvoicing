<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api } from '#lib/api';
	import type { Invoice, PaymentDocType, PaymentMethod } from '#lib/types';
	import { fmtEur, fmtDate, STATUS_LABELS, PAYMENT_METHODS, DOC_TYPE_LABELS } from '#lib/format';
	import { Button } from '#lib/components/ui/button';
	import { Badge } from '#lib/components/ui/badge';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import * as Table from '#lib/components/ui/table';
	import * as Dialog from '#lib/components/ui/dialog';
	import * as Select from '#lib/components/ui/select';
	import { Textarea } from '#lib/components/ui/textarea';
	import {
		Download,
		Send,
		XCircle,
		CheckCircle,
		Coins,
		FileText,
		Pencil,
		Trash2,
		Plus
	} from '@lucide/svelte';
	import type { InvoiceLine } from '#lib/types';

	let invoice = $state<Invoice | null>(null);
	let error = $state('');

	let payOpen = $state(false);
	let payEditId = $state<number | null>(null);
	let payForm = $state({
		amount: '',
		paid_at: new Date().toISOString().slice(0, 10),
		method: 'bank' as PaymentMethod,
		doc_type: 'kpo' as PaymentDocType,
		doc_number: '',
		note: ''
	});

	let editOpen = $state(false);
	let editForm = $state({
		issue_date: '',
		due_date: '',
		series: '',
		number: '' as string | number,
		notes: '',
		lines: [] as InvoiceLine[]
	});

	function openEdit() {
		if (!invoice) return;
		editForm = {
			issue_date: invoice.issue_date ?? '',
			due_date: invoice.due_date ?? '',
			series: invoice.series,
			number: invoice.number ?? '',
			notes: invoice.notes,
			lines: invoice.lines.map((l) => ({ ...l }))
		};
		editOpen = true;
	}

	async function saveEdit(e: SubmitEvent) {
		e.preventDefault();
		if (!invoice) return;
		try {
			invoice = await api<Invoice>(`/invoices/${id}`, {
				method: 'PUT',
				body: {
					client_id: invoice.client.id,
					issue_date: editForm.issue_date || null,
					due_date: editForm.due_date || null,
					series: editForm.series || null,
					number: editForm.number === '' ? null : Number(editForm.number),
					notes: editForm.notes,
					lines: editForm.lines
				}
			});
			editOpen = false;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		}
	}

	function openPayment(p?: Invoice['payments'][number]) {
		if (p) {
			payEditId = p.id ?? null;
			payForm = {
				amount: p.amount,
				paid_at: p.paid_at,
				method: p.method,
				doc_type: p.doc_type || ('kpo' as PaymentDocType),
				doc_number: p.doc_number,
				note: p.note
			};
		} else {
			payEditId = null;
			payForm.amount = String(
				Math.max(Number(invoice?.total ?? 0) - Number(invoice?.paid_total ?? 0), 0).toFixed(2)
			);
		}
		payOpen = true;
	}

	async function deletePayment(p: { id?: number }) {
		if (!p.id || !confirm('Ištrinti mokėjimą?')) return;
		await api(`/payments/${p.id}`, { method: 'DELETE' });
		await load();
	}

	let sendOpen = $state(false);
	let sendForm = $state({ to: '', subject: '', body: '' });
	let actionMsg = $state('');

	const id = $derived(page.params.id);

	async function load() {
		invoice = await api<Invoice>(`/invoices/${id}`);
	}

	onMount(load);

	async function issue() {
		invoice = await api<Invoice>(`/invoices/${id}/issue`, { method: 'POST', body: {} });
	}

	async function cancel() {
		const hasPayments = invoice?.payments.length;
		if (
			!confirm(
				hasPayments ? 'Anuliuoti sąskaitą? Visi mokėjimai bus ištrinti.' : 'Anuliuoti sąskaitą?'
			)
		)
			return;
		error = '';
		try {
			invoice = await api<Invoice>(`/invoices/${id}/cancel`, { method: 'POST' });
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		}
	}

	async function addPayment(e: SubmitEvent) {
		e.preventDefault();
		const body = { ...payForm, doc_type: payForm.method === 'cash' ? payForm.doc_type : '' };
		try {
			if (payEditId) {
				await api(`/payments/${payEditId}`, { method: 'PUT', body });
			} else {
				await api(`/invoices/${id}/payments`, { method: 'POST', body });
			}
			payOpen = false;
			await load();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		}
	}

	function openSend() {
		sendForm = {
			to: invoice?.client.email ?? '',
			subject: `Sąskaita faktūra ${invoice?.full_number ?? ''}`,
			body: ''
		};
		sendOpen = true;
	}

	async function send(e: SubmitEvent) {
		e.preventDefault();
		try {
			await api(`/invoices/${id}/send`, {
				method: 'POST',
				body: { to: sendForm.to || null, subject: sendForm.subject || null, body: sendForm.body }
			});
			sendOpen = false;
			actionMsg = 'Sąskaita įtraukta į siuntimo eilę.';
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		}
	}
</script>

{#if invoice}
	<div class="mb-6 flex flex-wrap items-center gap-3">
		<Button variant="ghost" href="/invoices">← Atgal</Button>
		<h1 class="text-2xl font-semibold">{invoice.full_number ?? 'Juodraštis'}</h1>
		<Badge>{STATUS_LABELS[invoice.status]}</Badge>
		<div class="ml-auto flex gap-2">
			{#if invoice.status === 'draft'}
				<Button onclick={issue}><CheckCircle class="size-4" /> Išrašyti</Button>
			{/if}
			{#if invoice.status !== 'cancelled'}
				<Button variant="outline" onclick={openEdit}><Pencil class="size-4" /> Redaguoti</Button>
			{/if}
			{#if invoice.status !== 'draft' && invoice.status !== 'cancelled'}
				<Button variant="outline" href="/api/v1/invoices/{invoice.id}/pdf" target="_blank">
					<Download class="size-4" /> PDF
				</Button>
				{#if invoice.payments.some((p) => p.doc_type)}
					<Button
						variant="outline"
						href="/api/v1/invoices/{invoice.id}/pdf?with_cash_docs=1"
						target="_blank"
					>
						<Download class="size-4" /> PDF + kasos dok.
					</Button>
				{/if}
				<Button variant="outline" onclick={openSend}><Send class="size-4" /> Siųsti</Button>
				<Button variant="outline" onclick={() => openPayment()}
					><Coins class="size-4" /> Mokėjimas</Button
				>
			{/if}
			{#if invoice.status !== 'cancelled'}
				<Button variant="destructive" onclick={cancel}><XCircle class="size-4" /> Anuliuoti</Button>
			{/if}
		</div>
	</div>

	{#if actionMsg}<p class="mb-4 text-sm text-green-600">{actionMsg}</p>{/if}
	{#if error}<p class="mb-4 text-sm text-destructive">{error}</p>{/if}

	<div class="grid gap-4 lg:grid-cols-3">
		<Card.Root class="lg:col-span-2">
			<Card.Header><Card.Title>Sąskaita</Card.Title></Card.Header>
			<Card.Content>
				<dl class="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
					<div>
						<dt class="text-muted-foreground">Klientas</dt>
						<dd class="font-medium">{invoice.client.name}</dd>
					</div>
					<div>
						<dt class="text-muted-foreground">Išrašyta</dt>
						<dd>{fmtDate(invoice.issue_date)}</dd>
					</div>
					<div>
						<dt class="text-muted-foreground">Apmokėti iki</dt>
						<dd>{fmtDate(invoice.due_date)}</dd>
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
						{#each invoice.lines as l (l.id)}
							<Table.Row>
								<Table.Cell>{l.description}</Table.Cell>
								<Table.Cell>{l.quantity}</Table.Cell>
								<Table.Cell>{l.unit}</Table.Cell>
								<Table.Cell class="text-right">{fmtEur(l.unit_price)}</Table.Cell>
								<Table.Cell class="text-right">{fmtEur(l.total ?? 0)}</Table.Cell>
							</Table.Row>
						{/each}
						<Table.Row class="font-semibold">
							<Table.Cell colspan={4} class="text-right">Iš viso</Table.Cell>
							<Table.Cell class="text-right">{fmtEur(invoice.total)}</Table.Cell>
						</Table.Row>
					</Table.Body>
				</Table.Root>
				{#if invoice.notes}<p class="mt-3 text-sm text-muted-foreground">{invoice.notes}</p>{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header><Card.Title>Mokėjimai</Card.Title></Card.Header>
			<Card.Content>
				{#if invoice.payments.length === 0}
					<p class="text-sm text-muted-foreground">Mokėjimų nėra.</p>
				{:else}
					<ul class="space-y-2 text-sm">
						{#each invoice.payments as p (p.id)}
							<li class="border-b pb-2 last:border-0">
								<div class="flex items-center justify-between">
									<span>{p.paid_at}</span>
									<span class="font-medium">{fmtEur(p.amount)}</span>
								</div>
								<div class="mt-0.5 flex items-center justify-between text-xs text-muted-foreground">
									<span>{PAYMENT_METHODS[p.method]}{p.doc_number ? ` · ${p.doc_number}` : ''}</span>
									<span class="flex items-center gap-1">
										{#if p.doc_type}
											<Button
												variant="ghost"
												size="sm"
												class="h-6 px-1 text-xs"
												href="/api/v1/payments/{p.id}/cash-doc.pdf"
												target="_blank"
											>
												<FileText class="size-3" />
												{p.doc_type.toUpperCase()}
											</Button>
										{/if}
										{#if invoice.status !== 'cancelled'}
											<Button
												variant="ghost"
												size="icon"
												class="h-6 w-6"
												onclick={() => openPayment(p)}><Pencil class="size-3" /></Button
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
						<span>Suma</span><span>{fmtEur(invoice.total)}</span>
					</div>
					<div class="flex justify-between">
						<span>Apmokėta</span><span>{fmtEur(invoice.paid_total)}</span>
					</div>
					<div class="flex justify-between font-semibold">
						<span>Likutis</span><span
							>{fmtEur(Number(invoice.total) - Number(invoice.paid_total))}</span
						>
					</div>
				</div>
			</Card.Content>
		</Card.Root>
	</div>
{:else}
	<p class="text-muted-foreground">Kraunama…</p>
{/if}

<Dialog.Root bind:open={editOpen}>
	<Dialog.Content class="max-h-[90vh] overflow-y-auto sm:max-w-4xl">
		<Dialog.Header><Dialog.Title>Redaguoti sąskaitą</Dialog.Title></Dialog.Header>
		<form onsubmit={saveEdit} class="space-y-3">
			<div class="grid grid-cols-4 gap-3">
				<div class="space-y-1.5">
					<Label>Serija</Label><Input bind:value={editForm.series} />
				</div>
				<div class="space-y-1.5">
					<Label>Numeris</Label><Input type="number" bind:value={editForm.number} />
				</div>
				<div class="space-y-1.5">
					<Label>Išrašymo data</Label><Input type="date" bind:value={editForm.issue_date} />
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
						})}><Plus class="size-4" /> Eilutė</Button
				>
			</div>
			<div class="space-y-1.5">
				<Label>Pastabos</Label><Textarea bind:value={editForm.notes} rows={2} />
			</div>
			<Dialog.Footer><Button type="submit">Išsaugoti pakeitimus</Button></Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={payOpen}>
	<Dialog.Content>
		<Dialog.Header
			><Dialog.Title>{payEditId ? 'Redaguoti mokėjimą' : 'Registruoti mokėjimą'}</Dialog.Title
			></Dialog.Header
		>
		<form onsubmit={addPayment} class="space-y-3">
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5">
					<Label>Suma EUR *</Label><Input
						type="number"
						step="0.01"
						min="0.01"
						bind:value={payForm.amount}
						required
					/>
				</div>
				<div class="space-y-1.5">
					<Label>Data *</Label><Input type="date" bind:value={payForm.paid_at} required />
				</div>
			</div>
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
							<Select.Trigger class="w-full">{DOC_TYPE_LABELS[payForm.doc_type]}</Select.Trigger>
							<Select.Content>
								{#each Object.entries(DOC_TYPE_LABELS) as [v, label] (v)}
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
					<Input bind:value={payForm.doc_number} placeholder="Tuščia – suteikiama automatiškai" />
				</div>
			{/if}
			<div class="space-y-1.5"><Label>Pastaba</Label><Input bind:value={payForm.note} /></div>
			<Dialog.Footer><Button type="submit">Išsaugoti</Button></Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={sendOpen}>
	<Dialog.Content>
		<Dialog.Header><Dialog.Title>Siųsti sąskaitą el. paštu</Dialog.Title></Dialog.Header>
		<form onsubmit={send} class="space-y-3">
			<div class="space-y-1.5">
				<Label>Gavėjas</Label><Input
					type="email"
					bind:value={sendForm.to}
					placeholder={invoice?.client.email || 'el. paštas'}
				/>
			</div>
			<div class="space-y-1.5"><Label>Tema</Label><Input bind:value={sendForm.subject} /></div>
			<div class="space-y-1.5">
				<Label>Tekstas</Label><Textarea
					bind:value={sendForm.body}
					rows={4}
					placeholder="Laba diena, siunčiame sąskaitą faktūrą."
				/>
			</div>
			<Dialog.Footer><Button type="submit"><Send class="size-4" /> Siųsti</Button></Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
