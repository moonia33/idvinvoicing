<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api';
	import type { Client, Invoice, Service } from '#lib/types';
	import { fmtEur } from '#lib/format';
	import { Button } from '#lib/components/ui/button';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import * as Select from '#lib/components/ui/select';
	import { Textarea } from '#lib/components/ui/textarea';
	import { Plus, Trash2 } from '@lucide/svelte';

	let clients = $state<Client[]>([]);
	let services = $state<Service[]>([]);
	let clientId = $state('');
	let dueDate = $state('');
	let notes = $state('');
	let lines = $state([
		{ description: '', quantity: '1', unit: 'vnt.', unit_price: '', service_id: '' }
	]);
	let error = $state('');
	let saving = $state(false);

	onMount(async () => {
		[clients, services] = await Promise.all([
			api<Client[]>('/clients'),
			api<Service[]>('/services')
		]);
	});

	let total = $derived(
		lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0)
	);

	function addLine() {
		lines = [
			...lines,
			{ description: '', quantity: '1', unit: 'vnt.', unit_price: '', service_id: '' }
		];
	}

	function pickService(i: number, serviceId: string | undefined) {
		const s = services.find((x) => String(x.id) === serviceId);
		if (!s) return;
		lines[i].description = s.name;
		lines[i].unit = s.unit;
		lines[i].unit_price = s.unit_price;
		lines[i].service_id = serviceId ?? '';
	}

	function removeLine(i: number) {
		lines = lines.filter((_, idx) => idx !== i);
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
</div>

<form onsubmit={save}>
	<Card.Root class="mx-auto max-w-3xl">
		<Card.Content class="space-y-5 pt-6">
			<div class="grid gap-4 sm:grid-cols-2">
				<div class="space-y-1.5">
					<Label>Klientas *</Label>
					<Select.Root type="single" bind:value={clientId}>
						<Select.Trigger class="w-full">
							{clients.find((c) => String(c.id) === clientId)?.name ?? 'Pasirinkite'}
						</Select.Trigger>
						<Select.Content>
							{#each clients as c (c.id)}
								<Select.Item value={String(c.id)} label={c.name}>{c.name}</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-1.5">
					<Label>Apmokėti iki</Label>
					<Input type="date" bind:value={dueDate} />
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
								<Select.Trigger class="w-52">
									{services.find((s) => String(s.id) === line.service_id)?.name ?? 'Iš katalogo…'}
								</Select.Trigger>
								<Select.Content>
									{#each services as s (s.id)}
										<Select.Item value={String(s.id)} label={s.name}>
											{s.code ? `${s.code} ` : ''}{s.name} – {fmtEur(s.unit_price)}
										</Select.Item>
									{/each}
								</Select.Content>
							</Select.Root>
							<Input
								class="flex-1"
								placeholder="Paslaugos aprašymas"
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
							<Input class="w-20" bind:value={line.unit} title="Vienetas" />
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

			<div class="flex items-center justify-between border-t pt-4">
				<span class="text-lg font-semibold">Iš viso: {fmtEur(total)}</span>
				<Button type="submit" disabled={saving || !clientId}>
					{saving ? 'Saugoma…' : 'Sukurti juodraštį'}
				</Button>
			</div>
			{#if error}<p class="text-sm text-destructive">{error}</p>{/if}
		</Card.Content>
	</Card.Root>
</form>
