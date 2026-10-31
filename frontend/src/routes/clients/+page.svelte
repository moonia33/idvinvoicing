<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api';
	import type { Contact } from '#lib/types';
	import { Button } from '#lib/components/ui/button';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import * as Table from '#lib/components/ui/table';
	import * as Dialog from '#lib/components/ui/dialog';
	import { Textarea } from '#lib/components/ui/textarea';
	import { Trash2 } from '@lucide/svelte';

	let clients = $state<Contact[]>([]);
	let open = $state(false);
	let editing = $state<Contact | null>(null);
	let form = $state({
		name: '',
		code: '',
		vat_code: '',
		email: '',
		address: '',
		is_client: true,
		is_supplier: false
	});
	let error = $state('');

	async function load() {
		clients = await api<Contact[]>('/clients');
	}

	onMount(load);

	function openCreate() {
		editing = null;
		form = {
			name: '',
			code: '',
			vat_code: '',
			email: '',
			address: '',
			is_client: true,
			is_supplier: false
		};
		open = true;
	}

	function openEdit(c: Contact) {
		editing = c;
		form = {
			name: c.name,
			code: c.code,
			vat_code: c.vat_code,
			email: c.email,
			address: c.address,
			is_client: c.is_client,
			is_supplier: c.is_supplier
		};
		open = true;
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		if (!form.is_client && !form.is_supplier) {
			error = 'Pažymėkite bent vieną rolę (klientas arba tiekėjas)';
			return;
		}
		try {
			if (editing) {
				await api(`/clients/${editing.id}`, { method: 'PUT', body: form });
			} else {
				await api('/clients', { method: 'POST', body: form });
			}
			open = false;
			await load();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
		}
	}

	async function remove(c: Contact) {
		if (!confirm(`Ištrinti klientą „${c.name}“?`)) return;
		await api(`/clients/${c.id}`, { method: 'DELETE' });
		await load();
	}
</script>

<div class="mb-6 flex items-center justify-between">
	<h1 class="text-2xl font-semibold">Klientai</h1>
	<Button onclick={openCreate}>Naujas klientas</Button>
</div>

<Card.Root>
	<Table.Root>
		<Table.Header>
			<Table.Row>
				<Table.Head>Pavadinimas</Table.Head>
				<Table.Head>Kodas</Table.Head>
				<Table.Head>PVM kodas</Table.Head>
				<Table.Head>El. paštas</Table.Head>
				<Table.Head class="w-16"></Table.Head>
			</Table.Row>
		</Table.Header>
		<Table.Body>
			{#each clients as c (c.id)}
				<Table.Row class="cursor-pointer" onclick={() => openEdit(c)}>
					<Table.Cell class="font-medium">{c.name}</Table.Cell>
					<Table.Cell>{c.code}</Table.Cell>
					<Table.Cell>{c.vat_code}</Table.Cell>
					<Table.Cell>{c.email}</Table.Cell>
					<Table.Cell>
						<Button
							variant="ghost"
							size="icon"
							onclick={(e: MouseEvent) => {
								e.stopPropagation();
								remove(c);
							}}
						>
							<Trash2 class="size-4" />
						</Button>
					</Table.Cell>
				</Table.Row>
			{/each}
			{#if clients.length === 0}
				<Table.Row
					><Table.Cell colspan={5} class="text-center text-muted-foreground"
						>Klientų nėra</Table.Cell
					></Table.Row
				>
			{/if}
		</Table.Body>
	</Table.Root>
</Card.Root>

<Dialog.Root bind:open>
	<Dialog.Content>
		<Dialog.Header>
			<Dialog.Title>{editing ? 'Redaguoti klientą' : 'Naujas klientas'}</Dialog.Title>
		</Dialog.Header>
		<form onsubmit={save} class="space-y-3">
			<div class="space-y-1.5">
				<Label>Pavadinimas *</Label><Input bind:value={form.name} required />
			</div>
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5"><Label>Įm. kodas</Label><Input bind:value={form.code} /></div>
				<div class="space-y-1.5"><Label>PVM kodas</Label><Input bind:value={form.vat_code} /></div>
			</div>
			<div class="space-y-1.5">
				<Label>El. paštas</Label><Input type="email" bind:value={form.email} />
			</div>
			<div class="space-y-1.5">
				<Label>Adresas</Label><Textarea bind:value={form.address} rows={2} />
			</div>
			<div class="flex gap-4 text-sm">
				<label class="flex items-center gap-2">
					<input type="checkbox" bind:checked={form.is_client} /> Klientas
				</label>
				<label class="flex items-center gap-2">
					<input type="checkbox" bind:checked={form.is_supplier} /> Tiekėjas
				</label>
			</div>
			{#if error}<p class="text-sm text-destructive">{error}</p>{/if}
			<Dialog.Footer>
				<Button type="submit">{editing ? 'Išsaugoti' : 'Sukurti'}</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
