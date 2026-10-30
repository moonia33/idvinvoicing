<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api';
	import type { Client, RecurringTemplate } from '#lib/types';
	import { fmtEur, fmtDate, FREQ_LABELS } from '#lib/format';
	import { Button } from '#lib/components/ui/button';
	import { Badge } from '#lib/components/ui/badge';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import * as Table from '#lib/components/ui/table';
	import * as Select from '#lib/components/ui/select';
	import * as Dialog from '#lib/components/ui/dialog';
	import { Trash2 } from '@lucide/svelte';

	let templates = $state<RecurringTemplate[]>([]);
	let clients = $state<Client[]>([]);
	let open = $state(false);
	let form = $state({
		client_id: '',
		frequency: 'monthly',
		next_run_date: new Date().toISOString().slice(0, 10),
		auto_send: false,
		email_to: '',
		description: '',
		unit_price: ''
	});

	async function load() {
		[templates, clients] = await Promise.all([
			api<RecurringTemplate[]>('/recurring'),
			api<Client[]>('/clients')
		]);
	}

	onMount(load);

	async function save(e: SubmitEvent) {
		e.preventDefault();
		await api('/recurring', {
			method: 'POST',
			body: {
				client_id: Number(form.client_id),
				frequency: form.frequency,
				next_run_date: form.next_run_date,
				auto_send: form.auto_send,
				email_to: form.email_to,
				lines: [
					{
						description: form.description,
						quantity: '1',
						unit: 'vnt.',
						unit_price: form.unit_price
					}
				]
			}
		});
		open = false;
		await load();
	}

	async function toggle(t: RecurringTemplate) {
		await api(`/recurring/${t.id}`, {
			method: 'PUT',
			body: {
				client_id: t.client.id,
				frequency: t.frequency,
				next_run_date: t.next_run_date,
				active: !t.active,
				auto_send: t.auto_send,
				email_to: t.email_to,
				notes: t.notes,
				lines: t.lines.map((l) => ({
					description: l.description,
					quantity: l.quantity,
					unit: l.unit,
					unit_price: l.unit_price
				}))
			}
		});
		await load();
	}

	async function remove(t: RecurringTemplate) {
		if (!confirm('Ištrinti šabloną?')) return;
		await api(`/recurring/${t.id}`, { method: 'DELETE' });
		await load();
	}
</script>

<div class="mb-6 flex items-center justify-between">
	<h1 class="text-2xl font-semibold">Pasikartojančios sąskaitos</h1>
	<Button onclick={() => (open = true)}>Naujas šablonas</Button>
</div>

<Card.Root>
	<Table.Root>
		<Table.Header>
			<Table.Row>
				<Table.Head>Klientas</Table.Head><Table.Head>Dažnumas</Table.Head>
				<Table.Head>Kitas vykdymas</Table.Head><Table.Head>Auto siuntimas</Table.Head>
				<Table.Head class="text-right">Suma</Table.Head><Table.Head>Būsena</Table.Head>
				<Table.Head class="w-24"></Table.Head>
			</Table.Row>
		</Table.Header>
		<Table.Body>
			{#each templates as t (t.id)}
				<Table.Row>
					<Table.Cell class="font-medium">{t.client.name}</Table.Cell>
					<Table.Cell>{FREQ_LABELS[t.frequency]}</Table.Cell>
					<Table.Cell>{fmtDate(t.next_run_date)}</Table.Cell>
					<Table.Cell>{t.auto_send ? 'Taip' : 'Ne'}</Table.Cell>
					<Table.Cell class="text-right">{fmtEur(t.lines[0]?.total ?? 0)}</Table.Cell>
					<Table.Cell
						><Badge variant={t.active ? 'default' : 'secondary'}
							>{t.active ? 'Aktyvus' : 'Išjungtas'}</Badge
						></Table.Cell
					>
					<Table.Cell class="flex gap-1">
						<Button variant="outline" size="sm" onclick={() => toggle(t)}
							>{t.active ? 'Stabdyti' : 'Įjungti'}</Button
						>
						<Button variant="ghost" size="icon" onclick={() => remove(t)}
							><Trash2 class="size-4" /></Button
						>
					</Table.Cell>
				</Table.Row>
			{/each}
			{#if templates.length === 0}
				<Table.Row
					><Table.Cell colspan={7} class="text-center text-muted-foreground"
						>Šablonų nėra</Table.Cell
					></Table.Row
				>
			{/if}
		</Table.Body>
	</Table.Root>
</Card.Root>

<Dialog.Root bind:open>
	<Dialog.Content>
		<Dialog.Header><Dialog.Title>Naujas pasikartojantis šablonas</Dialog.Title></Dialog.Header>
		<form onsubmit={save} class="space-y-3">
			<div class="space-y-1.5">
				<Label>Klientas *</Label>
				<Select.Root type="single" bind:value={form.client_id}>
					<Select.Trigger class="w-full">
						{clients.find((c) => String(c.id) === form.client_id)?.name ?? 'Pasirinkite'}
					</Select.Trigger>
					<Select.Content>
						{#each clients as c (c.id)}
							<Select.Item value={String(c.id)} label={c.name}>{c.name}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5">
					<Label>Dažnumas</Label>
					<Select.Root type="single" bind:value={form.frequency}>
						<Select.Trigger>{FREQ_LABELS[form.frequency]}</Select.Trigger>
						<Select.Content>
							{#each Object.entries(FREQ_LABELS) as [v, l] (v)}
								<Select.Item value={v} label={l}>{l}</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-1.5">
					<Label>Kitas vykdymas *</Label><Input
						type="date"
						bind:value={form.next_run_date}
						required
					/>
				</div>
			</div>
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5">
					<Label>Paslauga *</Label><Input bind:value={form.description} required />
				</div>
				<div class="space-y-1.5">
					<Label>Kaina EUR *</Label><Input
						type="number"
						step="0.01"
						min="0.01"
						bind:value={form.unit_price}
						required
					/>
				</div>
			</div>
			<label class="flex items-center gap-2 text-sm">
				<input type="checkbox" bind:checked={form.auto_send} /> Siųsti automatiškai el. paštu
			</label>
			{#if form.auto_send}
				<div class="space-y-1.5">
					<Label>Gavėjo el. paštas (jei tuščia – kliento)</Label><Input
						type="email"
						bind:value={form.email_to}
					/>
				</div>
			{/if}
			<Dialog.Footer
				><Button type="submit" disabled={!form.client_id}>Sukurti</Button></Dialog.Footer
			>
		</form>
	</Dialog.Content>
</Dialog.Root>
