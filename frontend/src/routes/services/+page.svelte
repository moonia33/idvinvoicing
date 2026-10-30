<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api';
	import type { Category, Service } from '#lib/types';
	import { fmtEur } from '#lib/format';
	import { Button } from '#lib/components/ui/button';
	import { Badge } from '#lib/components/ui/badge';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import * as Table from '#lib/components/ui/table';
	import * as Select from '#lib/components/ui/select';
	import * as Dialog from '#lib/components/ui/dialog';
	import { Trash2 } from '@lucide/svelte';

	let services = $state<Service[]>([]);
	let categories = $state<Category[]>([]);
	let open = $state(false);
	let editing = $state<Service | null>(null);
	let form = $state({
		code: '',
		name: '',
		category_id: '',
		unit: 'vnt.',
		unit_price: '',
		active: true
	});
	let error = $state('');

	async function load() {
		[services, categories] = await Promise.all([
			api<Service[]>('/services?all=true'),
			api<Category[]>('/ledger/categories?kind=income')
		]);
	}

	onMount(load);

	function openCreate() {
		editing = null;
		form = { code: '', name: '', category_id: '', unit: 'vnt.', unit_price: '', active: true };
		open = true;
	}

	function openEdit(s: Service) {
		editing = s;
		form = {
			code: s.code,
			name: s.name,
			category_id: s.category_id ? String(s.category_id) : '',
			unit: s.unit,
			unit_price: s.unit_price,
			active: s.active
		};
		open = true;
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		const body = {
			...form,
			category_id: form.category_id ? Number(form.category_id) : null
		};
		try {
			if (editing) {
				await api(`/services/${editing.id}`, { method: 'PUT', body });
			} else {
				await api('/services', { method: 'POST', body });
			}
			open = false;
			await load();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		}
	}

	async function remove(s: Service) {
		if (!confirm(`Ištrinti „${s.name}“?`)) return;
		await api(`/services/${s.id}`, { method: 'DELETE' });
		await load();
	}
</script>

<div class="mb-6 flex items-center justify-between">
	<h1 class="text-2xl font-semibold">Prekės ir paslaugos</h1>
	<Button onclick={openCreate}>Naujas įrašas</Button>
</div>

<Card.Root>
	<Table.Root>
		<Table.Header>
			<Table.Row>
				<Table.Head>Kodas</Table.Head>
				<Table.Head>Pavadinimas</Table.Head>
				<Table.Head>Kategorija</Table.Head>
				<Table.Head>Vnt.</Table.Head>
				<Table.Head class="text-right">Kaina</Table.Head>
				<Table.Head>Būsena</Table.Head>
				<Table.Head class="w-16"></Table.Head>
			</Table.Row>
		</Table.Header>
		<Table.Body>
			{#each services as s (s.id)}
				<Table.Row class="cursor-pointer" onclick={() => openEdit(s)}>
					<Table.Cell>{s.code}</Table.Cell>
					<Table.Cell class="font-medium">{s.name}</Table.Cell>
					<Table.Cell>{categories.find((c) => c.id === s.category_id)?.name ?? ''}</Table.Cell>
					<Table.Cell>{s.unit}</Table.Cell>
					<Table.Cell class="text-right">{fmtEur(s.unit_price)}</Table.Cell>
					<Table.Cell>
						<Badge variant={s.active ? 'default' : 'secondary'}>
							{s.active ? 'Aktyvus' : 'Išjungtas'}
						</Badge>
					</Table.Cell>
					<Table.Cell>
						<Button
							variant="ghost"
							size="icon"
							onclick={(e: MouseEvent) => {
								e.stopPropagation();
								remove(s);
							}}
						>
							<Trash2 class="size-4" />
						</Button>
					</Table.Cell>
				</Table.Row>
			{/each}
			{#if services.length === 0}
				<Table.Row>
					<Table.Cell colspan={7} class="text-center text-muted-foreground">
						Įrašų nėra – sukurkite paslaugų/prekių katalogą sąskaitoms
					</Table.Cell>
				</Table.Row>
			{/if}
		</Table.Body>
	</Table.Root>
</Card.Root>

<Dialog.Root bind:open>
	<Dialog.Content>
		<Dialog.Header>
			<Dialog.Title>{editing ? 'Redaguoti įrašą' : 'Nauja prekė/paslauga'}</Dialog.Title>
		</Dialog.Header>
		<form onsubmit={save} class="space-y-3">
			<div class="grid grid-cols-3 gap-3">
				<div class="col-span-2 space-y-1.5">
					<Label>Pavadinimas *</Label><Input bind:value={form.name} required />
				</div>
				<div class="space-y-1.5"><Label>Kodas</Label><Input bind:value={form.code} /></div>
			</div>
			<div class="space-y-1.5">
				<Label>Kategorija (pajamų)</Label>
				<Select.Root type="single" bind:value={form.category_id}>
					<Select.Trigger class="w-full">
						{categories.find((c) => String(c.id) === form.category_id)?.name ?? 'Be kategorijos'}
					</Select.Trigger>
					<Select.Content>
						{#each categories as c (c.id)}
							<Select.Item value={String(c.id)} label={c.name}>{c.name}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5"><Label>Vienetas</Label><Input bind:value={form.unit} /></div>
				<div class="space-y-1.5">
					<Label>Kaina EUR *</Label>
					<Input type="number" step="0.01" min="0" bind:value={form.unit_price} required />
				</div>
			</div>
			<label class="flex items-center gap-2 text-sm">
				<input type="checkbox" bind:checked={form.active} /> Aktyvus (rodomas sąskaitose)
			</label>
			{#if error}<p class="text-sm text-destructive">{error}</p>{/if}
			<Dialog.Footer
				><Button type="submit">{editing ? 'Išsaugoti' : 'Sukurti'}</Button></Dialog.Footer
			>
		</form>
	</Dialog.Content>
</Dialog.Root>
