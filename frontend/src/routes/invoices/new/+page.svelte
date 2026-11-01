<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api';
	import type { Contact, Invoice, Service } from '#lib/types';
	import { fmtEur, UNITS } from '#lib/format';
	import { Button } from '#lib/components/ui/button';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import * as Select from '#lib/components/ui/select';
	import * as Dialog from '#lib/components/ui/dialog';
	import { Textarea } from '#lib/components/ui/textarea';
	import { Plus, Trash2 } from '@lucide/svelte';

	type Line = {
		description: string;
		quantity: string;
		unit: string;
		unit_price: string;
		service_id: string;
	};
	const emptyLine = (): Line => ({
		description: '',
		quantity: '1',
		unit: 'vnt.',
		unit_price: '',
		service_id: ''
	});

	let clients = $state<Contact[]>([]);
	let services = $state<Service[]>([]);
	let clientId = $state('');
	let issueDate = $state(new Date().toISOString().slice(0, 10));
	let dueDate = $state('');
	let issueNow = $state(true);
	let nextNumber = $state('');
	let notes = $state('');
	let lines = $state<Line[]>([emptyLine()]);
	let error = $state('');
	let saving = $state(false);

	// quick-create
	let clientDialog = $state(false);
	let clientForm = $state({ name: '', code: '', vat_code: '', email: '', address: '' });
	let serviceDialog = $state(false);
	let serviceForm = $state({ name: '', code: '', unit: 'vnt.', unit_price: '' });
	let serviceLineIdx = $state(0);

	onMount(async () => {
		[clients, services] = await Promise.all([
			api<Contact[]>('/clients'),
			api<Service[]>('/services?usage=sale')
		]);
	});

	$effect(() => {
		const y = issueDate.slice(0, 4);
		api<{ full_number: string }>(`/invoices/next-number?year=${y}`)
			.then((r) => (nextNumber = r.full_number))
			.catch(() => (nextNumber = ''));
	});

	let total = $derived(
		lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0)
	);

	function addLine() {
		lines = [...lines, emptyLine()];
	}

	function removeLine(i: number) {
		lines = lines.filter((_, idx) => idx !== i);
	}

	function pickService(i: number, serviceId: string | undefined) {
		const s = services.find((x) => String(x.id) === serviceId);
		if (!s) return;
		lines[i].description = s.name;
		lines[i].unit = s.unit;
		lines[i].unit_price = s.unit_price;
		lines[i].service_id = serviceId ?? '';
	}

	async function createClient(e: SubmitEvent) {
		e.preventDefault();
		const c = await api<Contact>('/clients', { method: 'POST', body: clientForm });
		clients = [...clients, c];
		clientId = String(c.id);
		clientDialog = false;
		clientForm = { name: '', code: '', vat_code: '', email: '', address: '' };
	}

	function openServiceDialog(i: number) {
		serviceLineIdx = i;
		serviceForm = { name: '', code: '', unit: 'vnt.', unit_price: '' };
		serviceDialog = true;
	}

	async function createService(e: SubmitEvent) {
		e.preventDefault();
		const s = await api<Service>('/services', { method: 'POST', body: serviceForm });
		services = [...services, s];
		pickService(serviceLineIdx, String(s.id));
		serviceDialog = false;
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		saving = true;
		try {
			const inv = await api<Invoice>('/invoices', {
				method: 'POST',
				body: {
					client_id: Number(clientId),
					due_date: dueDate || null,
					notes,
					lines: lines.map((l) => ({
						description: l.description,
						quantity: l.quantity || '1',
						unit: l.unit,
						unit_price: l.unit_price
					}))
				}
			});
			if (issueNow) {
				await api(`/invoices/${inv.id}/issue`, {
					method: 'POST',
					body: { issue_date: issueDate, due_date: dueDate || null }
				});
			}
			goto(resolve('/invoices/[id]', { id: String(inv.id) }));
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
			saving = false;
		}
	}
</script>

<div class="mb-6 flex items-center gap-3">
	<Button variant="ghost" href={resolve('/invoices')}>← Atgal</Button>
	<h1 class="text-2xl font-semibold">Nauja sąskaita</h1>
	{#if nextNumber}<span class="text-sm text-muted-foreground">Nr.: {nextNumber}</span>{/if}
</div>

<form onsubmit={save}>
	<Card.Root class="mx-auto max-w-3xl">
		<Card.Content class="space-y-5 pt-6">
			<div class="grid gap-4 sm:grid-cols-2">
				<div class="space-y-1.5">
					<Label>Klientas *</Label>
					<div class="flex gap-2">
						<Select.Root type="single" bind:value={clientId}>
							<Select.Trigger class="w-full">
								{clients.find((c) => String(c.id) === clientId)?.name ?? 'Pasirinkite'}
							</Select.Trigger>
							<Select.Content>
								{#each clients as c (c.id)}
									<Select.Item value={String(c.id)} label={c.name}>{c.name}</Select.Item>
								{/each}
								{#if clients.length === 0}
									<div class="px-3 py-2 text-sm text-muted-foreground">
										Klientų nėra – sukurkite mygtuku „+“
									</div>
								{/if}
							</Select.Content>
						</Select.Root>
						<Button
							variant="outline"
							size="icon"
							type="button"
							onclick={() => (clientDialog = true)}
							title="Naujas klientas"
						>
							<Plus class="size-4" />
						</Button>
					</div>
				</div>
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-1.5">
						<Label>Sąskaitos data</Label>
						<Input type="date" bind:value={issueDate} disabled={!issueNow} />
					</div>
					<div class="space-y-1.5">
						<Label>Apmokėti iki</Label>
						<Input type="date" bind:value={dueDate} />
					</div>
				</div>
			</div>

			<div>
				<Label class="mb-2 block">Eilutės *</Label>
				<div class="space-y-2">
					{#each lines as line, i (i)}
						<div class="flex items-center gap-2">
							<Select.Root
								type="single"
								value={line.service_id}
								onValueChange={(v) => pickService(i, v)}
							>
								<Select.Trigger class="w-48">
									{services.find((s) => String(s.id) === line.service_id)?.name ?? 'Iš katalogo…'}
								</Select.Trigger>
								<Select.Content>
									{#each services as s (s.id)}
										<Select.Item value={String(s.id)} label={s.name}>
											{s.code ? `${s.code} ` : ''}{s.name} – {fmtEur(s.unit_price)}
										</Select.Item>
									{/each}
									{#if services.length === 0}
										<div class="px-3 py-2 text-sm text-muted-foreground">
											Katalogas tuščias – sukurkite „+“
										</div>
									{/if}
								</Select.Content>
							</Select.Root>
							<Button
								variant="outline"
								size="icon"
								type="button"
								onclick={() => openServiceDialog(i)}
								title="Nauja paslauga"
							>
								<Plus class="size-4" />
							</Button>
							<Input
								class="flex-1"
								placeholder="Aprašymas"
								bind:value={line.description}
								required
							/>
							<Input
								class="w-20"
								type="number"
								step="0.01"
								min="0.01"
								bind:value={line.quantity}
								title="Kiekis"
							/>
							<Select.Root type="single" bind:value={line.unit}>
								<Select.Trigger class="w-20">{line.unit}</Select.Trigger>
								<Select.Content>
									{#each UNITS as u (u)}
										<Select.Item value={u} label={u}>{u}</Select.Item>
									{/each}
								</Select.Content>
							</Select.Root>
							<Input
								class="w-28"
								type="number"
								step="0.01"
								min="0"
								placeholder="Kaina EUR"
								bind:value={line.unit_price}
								required
							/>
							<Button
								variant="ghost"
								size="icon"
								type="button"
								onclick={() => removeLine(i)}
								disabled={lines.length === 1}
							>
								<Trash2 class="size-4" />
							</Button>
						</div>
					{/each}
				</div>
				<Button variant="outline" size="sm" type="button" class="mt-2" onclick={addLine}>
					<Plus class="size-4" /> Pridėti eilutę
				</Button>
			</div>

			<div class="space-y-1.5">
				<Label>Pastabos</Label>
				<Textarea bind:value={notes} rows={2} />
			</div>

			<div class="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={issueNow} /> Išrašyti iš karto (suteikti numerį)
				</label>
				<span class="text-lg font-semibold">Iš viso: {fmtEur(total)}</span>
				<Button type="submit" disabled={saving || !clientId}>
					{saving ? 'Saugoma…' : issueNow ? 'Išrašyti sąskaitą' : 'Sukurti juodraštį'}
				</Button>
			</div>
			{#if error}<p class="text-sm text-destructive">{error}</p>{/if}
		</Card.Content>
	</Card.Root>
</form>

<Dialog.Root bind:open={clientDialog}>
	<Dialog.Content>
		<Dialog.Header><Dialog.Title>Naujas klientas</Dialog.Title></Dialog.Header>
		<form onsubmit={createClient} class="space-y-3">
			<div class="space-y-1.5">
				<Label>Pavadinimas *</Label><Input bind:value={clientForm.name} required />
			</div>
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5"><Label>Kodas</Label><Input bind:value={clientForm.code} /></div>
				<div class="space-y-1.5">
					<Label>PVM kodas</Label><Input bind:value={clientForm.vat_code} />
				</div>
			</div>
			<div class="space-y-1.5">
				<Label>El. paštas</Label><Input type="email" bind:value={clientForm.email} />
			</div>
			<Dialog.Footer><Button type="submit">Sukurti</Button></Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={serviceDialog}>
	<Dialog.Content>
		<Dialog.Header><Dialog.Title>Nauja prekė/paslauga</Dialog.Title></Dialog.Header>
		<form onsubmit={createService} class="space-y-3">
			<div class="grid grid-cols-3 gap-3">
				<div class="col-span-2 space-y-1.5">
					<Label>Pavadinimas *</Label><Input bind:value={serviceForm.name} required />
				</div>
				<div class="space-y-1.5"><Label>Kodas</Label><Input bind:value={serviceForm.code} /></div>
			</div>
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5">
					<Label>Vienetas</Label>
					<Select.Root type="single" bind:value={serviceForm.unit}>
						<Select.Trigger>{serviceForm.unit}</Select.Trigger>
						<Select.Content>
							{#each UNITS as u (u)}<Select.Item value={u} label={u}>{u}</Select.Item>{/each}
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-1.5">
					<Label>Kaina EUR *</Label><Input
						type="number"
						step="0.01"
						min="0"
						bind:value={serviceForm.unit_price}
						required
					/>
				</div>
			</div>
			<Dialog.Footer><Button type="submit">Sukurti</Button></Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
