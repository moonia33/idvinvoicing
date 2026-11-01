<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api';
	import type { Journal, LedgerEntry } from '#lib/types';
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

	const now = new Date();
	let year = $state(now.getFullYear());
	let month = $state(now.getMonth() + 1);
	let journal = $state<Journal | null>(null);
	let entries = $state<LedgerEntry[]>([]);

	let open = $state(false);
	let form = $state({
		kind: 'expense',
		category_id: '',
		document_date: now.toISOString().slice(0, 10),
		counterparty: '',
		description: '',
		currency: 'EUR',
		amount_original: '',
		exchange_rate: '1',
		deductible: true,
		tax_kind: 'none',
		tax_year: ''
	});

	const TAX_KINDS: Record<string, string> = {
		gpm: 'GPM',
		vsd: 'VSD',
		psd: 'PSD'
	};

	let counterparties = $state<string[]>([]);

	const MONTH_NAMES = [
		'',
		'Sausis',
		'Vasaris',
		'Kovas',
		'Balandis',
		'Gegužė',
		'Birželis',
		'Liepa',
		'Rugpjūtis',
		'Rugsėjis',
		'Spalis',
		'Lapkritis',
		'Gruodis'
	];

	const byMonth = $derived.by(() => {
		const rows = journal?.rows ?? [];
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- skaičiavime naudojamas laikinas Map, ne reaktyvi būsena
		const groups = new Map<number, typeof rows>();
		for (const r of rows) {
			const m = Number(r.date.slice(5, 7));
			if (!groups.has(m)) groups.set(m, []);
			groups.get(m)!.push(r);
		}
		return [...groups.entries()].map(([m, rs]) => ({
			month: m,
			rows: rs,
			income: rs.filter((x) => x.kind === 'income').reduce((a, x) => a + Number(x.amount), 0),
			expense: rs.filter((x) => x.kind === 'expense').reduce((a, x) => a + Number(x.amount), 0)
		}));
	});

	async function load() {
		[journal, entries] = await Promise.all([
			api<Journal>(`/ledger/journal?year=${year}&month=${month}`),
			api<LedgerEntry[]>(`/ledger/entries?year=${year}`)
		]);
	}

	onMount(async () => {
		await load();
		const cps = await api<{ name: string }[]>('/counterparties');
		counterparties = cps.map((c) => c.name);
	});

	async function saveEntry(e: SubmitEvent) {
		e.preventDefault();
		await api('/ledger/entries', {
			method: 'POST',
			body: {
				...form,
				category_id: form.category_id ? Number(form.category_id) : null,
				paid_date: form.document_date,
				tax_kind: form.tax_kind === 'none' ? '' : form.tax_kind,
				tax_year: form.tax_kind !== 'none' && form.tax_year ? Number(form.tax_year) : null
			}
		});
		open = false;
		await load();
	}

	async function removeEntry(en: LedgerEntry) {
		if (!confirm('Ištrinti įrašą?')) return;
		await api(`/ledger/entries/${en.id}`, { method: 'DELETE' });
		await load();
	}
</script>

<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
	<h1 class="text-2xl font-semibold">Pajamų-išlaidų žurnalas</h1>
	<div class="flex items-center gap-2">
		<Input type="number" class="w-24" bind:value={year} onchange={load} min="2000" />
		<Select.Root
			type="single"
			value={String(month)}
			onValueChange={(v) => {
				month = Number(v);
				load();
			}}
		>
			<Select.Trigger class="w-36">{month === 0 ? 'Visi metai' : `${month} mėn.`}</Select.Trigger>
			<Select.Content>
				<Select.Item value="0" label="Visi metai">Visi metai</Select.Item>
				{#each Array.from({ length: 12 }, (_, i) => i + 1) as m (m)}
					<Select.Item value={String(m)} label="{m} mėn.">{m} mėn.</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>
		<Button onclick={() => (open = true)}>Naujas įrašas</Button>
	</div>
</div>

{#if journal}
	<div class="mb-4 grid gap-3 sm:grid-cols-4">
		<Card.Root
			><Card.Content class="pt-4"
				><div class="text-xs text-muted-foreground">Pajamos</div>
				<div class="text-xl font-semibold">{fmtEur(journal.income_total)}</div></Card.Content
			></Card.Root
		>
		<Card.Root
			><Card.Content class="pt-4"
				><div class="text-xs text-muted-foreground">Išlaidos</div>
				<div class="text-xl font-semibold">{fmtEur(journal.expense_total)}</div></Card.Content
			></Card.Root
		>
		<Card.Root
			><Card.Content class="pt-4"
				><div class="text-xs text-muted-foreground">Atskaitymai</div>
				<div class="text-xl font-semibold">{fmtEur(journal.deductible_total)}</div></Card.Content
			></Card.Root
		>
		<Card.Root
			><Card.Content class="pt-4"
				><div class="text-xs text-muted-foreground">Pajamos − išlaidos</div>
				<div class="text-xl font-semibold">{fmtEur(journal.net)}</div></Card.Content
			></Card.Root
		>
	</div>
{/if}

<Card.Root class="mb-6">
	<Table.Root>
		<Table.Header>
			<Table.Row>
				<Table.Head>Data</Table.Head><Table.Head>Tipas</Table.Head><Table.Head>Aprašymas</Table.Head
				>
				<Table.Head>Kontragentas</Table.Head><Table.Head class="text-right">Suma</Table.Head>
			</Table.Row>
		</Table.Header>
		<Table.Body>
			{#if month === 0}
				{#each byMonth as g (g.month)}
					<Table.Row class="bg-muted/50 font-medium">
						<Table.Cell colspan={3}>{MONTH_NAMES[g.month]}</Table.Cell>
						<Table.Cell class="text-muted-foreground">{g.rows.length} įraš.</Table.Cell>
						<Table.Cell class="text-right">{fmtEur(g.income - g.expense)}</Table.Cell>
					</Table.Row>
					{#each g.rows as r, i (i)}
						<Table.Row>
							<Table.Cell>{r.date}</Table.Cell>
							<Table.Cell
								><Badge variant={r.kind === 'income' ? 'default' : 'secondary'}
									>{r.kind === 'income' ? 'Pajamos' : 'Išlaidos'}</Badge
								></Table.Cell
							>
							<Table.Cell>{r.description} {r.deductible ? '·atsk.' : ''}</Table.Cell>
							<Table.Cell>{r.counterparty}</Table.Cell>
							<Table.Cell class="text-right">{fmtEur(r.amount)}</Table.Cell>
						</Table.Row>
					{/each}
				{/each}
			{:else}
				{#each journal?.rows ?? [] as r, i (i)}
					<Table.Row>
						<Table.Cell>{r.date}</Table.Cell>
						<Table.Cell
							><Badge variant={r.kind === 'income' ? 'default' : 'secondary'}
								>{r.kind === 'income' ? 'Pajamos' : 'Išlaidos'}</Badge
							></Table.Cell
						>
						<Table.Cell>{r.description} {r.deductible ? '·atsk.' : ''}</Table.Cell>
						<Table.Cell>{r.counterparty}</Table.Cell>
						<Table.Cell class="text-right">{fmtEur(r.amount)}</Table.Cell>
					</Table.Row>
				{/each}
			{/if}
		</Table.Body>
	</Table.Root>
</Card.Root>

<Card.Root>
	<Card.Header><Card.Title class="text-base">Metų įrašai</Card.Title></Card.Header>
	<Table.Root>
		<Table.Header>
			<Table.Row>
				<Table.Head>Data</Table.Head><Table.Head>Tipas</Table.Head><Table.Head
					>Kontragentas</Table.Head
				>
				<Table.Head>Valiuta</Table.Head><Table.Head class="text-right">Originalu</Table.Head>
				<Table.Head class="text-right">EUR</Table.Head><Table.Head class="w-10"></Table.Head>
			</Table.Row>
		</Table.Header>
		<Table.Body>
			{#each entries as en (en.id)}
				<Table.Row>
					<Table.Cell>{en.document_date}</Table.Cell>
					<Table.Cell>
						{en.kind === 'income' ? 'Paj.' : 'Išl.'}{en.tax_kind
							? ` · ${en.tax_kind.toUpperCase()}`
							: ''}
					</Table.Cell>
					<Table.Cell>{en.counterparty}</Table.Cell>
					<Table.Cell
						>{en.currency}{en.currency === 'PLN' ? ` @${en.exchange_rate}` : ''}</Table.Cell
					>
					<Table.Cell class="text-right">{en.amount_original}</Table.Cell>
					<Table.Cell class="text-right">{fmtEur(en.amount_eur)}</Table.Cell>
					<Table.Cell
						><Button variant="ghost" size="icon" onclick={() => removeEntry(en)}
							><Trash2 class="size-4" /></Button
						></Table.Cell
					>
				</Table.Row>
			{/each}
		</Table.Body>
	</Table.Root>
</Card.Root>

<Dialog.Root bind:open>
	<Dialog.Content>
		<Dialog.Header><Dialog.Title>Naujas žurnalo įrašas</Dialog.Title></Dialog.Header>
		<form onsubmit={saveEntry} class="space-y-3">
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5">
					<Label>Tipas</Label>
					<Select.Root type="single" bind:value={form.kind}>
						<Select.Trigger>{form.kind === 'income' ? 'Pajamos' : 'Išlaidos'}</Select.Trigger>
						<Select.Content>
							<Select.Item value="expense" label="Išlaidos">Išlaidos</Select.Item>
							<Select.Item value="income" label="Pajamos">Pajamos</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-1.5">
					<Label>Data *</Label><Input type="date" bind:value={form.document_date} required />
				</div>
			</div>
			<div class="space-y-1.5">
				<Label>Kontragentas</Label>
				<Input
					bind:value={form.counterparty}
					list="cp-list"
					placeholder="Klientas arba tiekėjas…"
				/>
				<datalist id="cp-list">
					{#each counterparties as n (n)}<option value={n}></option>{/each}
				</datalist>
			</div>
			<div class="space-y-1.5"><Label>Aprašymas</Label><Input bind:value={form.description} /></div>
			<div class="grid grid-cols-3 gap-3">
				<div class="space-y-1.5">
					<Label>Valiuta</Label>
					<Select.Root type="single" bind:value={form.currency}>
						<Select.Trigger>{form.currency}</Select.Trigger>
						<Select.Content>
							<Select.Item value="EUR" label="EUR">EUR</Select.Item>
							<Select.Item value="PLN" label="PLN">PLN</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-1.5">
					<Label>Suma *</Label><Input
						type="number"
						step="0.01"
						min="0.01"
						bind:value={form.amount_original}
						required
					/>
				</div>
				{#if form.currency === 'PLN'}
					<div class="space-y-1.5">
						<Label>Kursas PLN→EUR *</Label><Input
							type="number"
							step="0.0001"
							min="0.0001"
							bind:value={form.exchange_rate}
							required
						/>
					</div>
				{/if}
			</div>
			{#if form.currency === 'PLN' && form.amount_original}
				<p class="text-sm text-muted-foreground">
					≈ {fmtEur(Number(form.amount_original) * Number(form.exchange_rate))} EUR
				</p>
			{/if}
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5">
					<Label>Mokesčio įmoka</Label>
					<Select.Root type="single" bind:value={form.tax_kind}>
						<Select.Trigger
							>{form.tax_kind === 'none' ? 'Ne mokestis' : TAX_KINDS[form.tax_kind]}</Select.Trigger
						>
						<Select.Content>
							<Select.Item value="none" label="Ne mokestis">Ne mokestis</Select.Item>
							{#each Object.entries(TAX_KINDS) as [v, l] (v)}
								<Select.Item value={v} label={l}>{l}</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
				{#if form.tax_kind !== 'none'}
					<div class="space-y-1.5">
						<Label>Už metus *</Label>
						<Input
							type="number"
							bind:value={form.tax_year}
							min="2000"
							placeholder={String(year)}
							required
						/>
					</div>
				{/if}
			</div>
			<label class="flex items-center gap-2 text-sm">
				<input type="checkbox" bind:checked={form.deductible} /> Leidžiami atskaitymai
				{#if form.tax_kind === 'gpm'}<span class="text-muted-foreground"
						>(GPM nėra atskaitymas)</span
					>{/if}
			</label>
			<Dialog.Footer><Button type="submit">Išsaugoti</Button></Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
