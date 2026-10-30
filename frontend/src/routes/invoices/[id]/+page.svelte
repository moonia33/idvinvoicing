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
	import { Download, Send, XCircle, CheckCircle, Coins, FileText } from '@lucide/svelte';

	let invoice = $state<Invoice | null>(null);
	let error = $state('');

	let payOpen = $state(false);
	let payForm = $state({
		amount: '',
		paid_at: new Date().toISOString().slice(0, 10),
		method: 'bank' as PaymentMethod,
		doc_type: 'kpo' as PaymentDocType,
		doc_number: '',
		note: ''
	});

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
		if (!confirm('Anuliuoti sąskaitą?')) return;
		invoice = await api<Invoice>(`/invoices/${id}/cancel`, { method: 'POST' });
	}

	async function addPayment(e: SubmitEvent) {
		e.preventDefault();
		try {
			await api(`/invoices/${id}/payments`, {
				method: 'POST',
				body: { ...payForm, doc_type: payForm.method === 'cash' ? payForm.doc_type : '' }
			});
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
				<Button variant="outline" onclick={() => (payOpen = true)}
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

<Dialog.Root bind:open={payOpen}>
	<Dialog.Content>
		<Dialog.Header><Dialog.Title>Registruoti mokėjimą</Dialog.Title></Dialog.Header>
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
