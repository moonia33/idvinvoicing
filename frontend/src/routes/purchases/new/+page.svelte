<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api';
	import type {
		Category,
		Contact,
		PaymentMethod,
		Purchase,
		PurchaseDocKind,
		Service
	} from '#lib/types';
	import { fmtEur, UNITS, CURRENCIES, PURCHASE_DOC_KINDS, PAYMENT_METHODS } from '#lib/format';
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

	let suppliers = $state<Contact[]>([]);
	let services = $state<Service[]>([]);
	let categories = $state<Category[]>([]);
	let supplierId = $state('');
	let docType = $state<PurchaseDocKind>('sf');
	let docNumber = $state('');
	let documentDate = $state(new Date().toISOString().slice(0, 10));
	let dueDate = $state('');
	let currency = $state<'EUR' | 'PLN'>('EUR');
	let exchangeRate = $state('1');
	let categoryId = $state('');
	let deductible = $state(true);
	let paidNow = $state(false);
	let paidMethod = $state<PaymentMethod>('bank');
	let paidDocNumber = $state('');
	let notes = $state('');

	$effect(() => {
		if (paidNow) paidMethod = docType === 'sf' ? 'bank' : 'cash';
	});
	let lines = $state<Line[]>([emptyLine()]);
	let error = $state('');
	let saving = $state(false);

	let supplierDialog = $state(false);
	let supplierForm = $state({ name: '', code: '', vat_code: '', email: '', address: '' });
	let serviceDialog = $state(false);
	let serviceForm = $state({ name: '', code: '', unit: 'vnt.', unit_price: '' });
	let serviceLineIdx = $state(0);

	onMount(async () => {
		[suppliers, categories, services] = await Promise.all([
			api<Contact[]>('/suppliers'),
			api<Category[]>('/ledger/categories?kind=expense'),
			api<Service[]>('/services?usage=purchase')
		]);
	});

	let total = $derived(
		lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0)
	);
	let totalEur = $derived(total * (Number(exchangeRate) || 0));

	function addLine() {
		lines = [...lines, emptyLine()];
	}

	function removeLine(i: number) {
		lines = lines.filter((_, idx) => idx !== i);
	}

	async function createSupplier(e: SubmitEvent) {
		e.preventDefault();
		const s = await api<Contact>('/suppliers', { method: 'POST', body: supplierForm });
		suppliers = [...suppliers, s];
		supplierId = String(s.id);
		supplierDialog = false;
		supplierForm = { name: '', code: '', vat_code: '', email: '', address: '' };
	}

	function pickService(i: number, serviceId: string | undefined) {
		const s = services.find((x) => String(x.id) === serviceId);
		if (!s) return;
		lines[i].description = s.name;
		lines[i].unit = s.unit;
		lines[i].unit_price = s.unit_price;
		lines[i].service_id = serviceId ?? '';
	}

	function openServiceDialog(i: number) {
		serviceLineIdx = i;
		serviceForm = { name: '', code: '', unit: 'vnt.', unit_price: '' };
		serviceDialog = true;
	}

	async function createService(e: SubmitEvent) {
		e.preventDefault();
		const s = await api<Service>('/services', {
			method: 'POST',
			body: { ...serviceForm, is_sale: false, is_purchase: true }
		});
		services = [...services, s];
		pickService(serviceLineIdx, String(s.id));
		serviceDialog = false;
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		saving = true;
		try {
			const p = await api<Purchase>('/purchases', {
				method: 'POST',
				body: {
					supplier_id: Number(supplierId),
					doc_type: docType,
					doc_number: docNumber,
					document_date: documentDate,
					due_date: dueDate || null,
					currency,
					exchange_rate: exchangeRate || '1',
					category_id: categoryId ? Number(categoryId) : null,
					deductible,
					paid_now: paidNow,
					paid_method: paidNow ? paidMethod : null,
					paid_doc_number: paidNow ? paidDocNumber : '',
					notes,
					lines: lines.map((l) => ({
						description: l.description,
						quantity: l.quantity || '1',
						unit: l.unit,
						unit_price: l.unit_price
					}))
				}
			});
			goto(resolve('/purchases/[id]', { id: String(p.id) }));
		} catch (err) {
			error = err instanceof Error ? err.message : 'Klaida';
			saving = false;
		}
	}
</script>

<div class="mb-6 flex items-center gap-3">
	<Button variant="ghost" href={resolve('/purchases')}>← Atgal</Button>
	<h1 class="text-2xl font-semibold">Naujas pirkinys</h1>
</div>

<form onsubmit={save}>
	<Card.Root class="mx-auto max-w-3xl">
		<Card.Content class="space-y-5 pt-6">
			<div class="grid gap-4 sm:grid-cols-2">
				<div class="space-y-1.5">
					<Label>Tiekėjas *</Label>
					<div class="flex gap-2">
						<Select.Root type="single" bind:value={supplierId}>
							<Select.Trigger class="w-full">
								{suppliers.find((s) => String(s.id) === supplierId)?.name ?? 'Pasirinkite'}
							</Select.Trigger>
							<Select.Content>
								{#each suppliers as s (s.id)}
									<Select.Item value={String(s.id)} label={s.name}>{s.name}</Select.Item>
								{/each}
								{#if suppliers.length === 0}
									<div class="px-3 py-2 text-sm text-muted-foreground">
										Tiekėjų nėra – sukurkite mygtuku „+“
									</div>
								{/if}
							</Select.Content>
						</Select.Root>
						<Button
							variant="outline"
							size="icon"
							type="button"
							onclick={() => (supplierDialog = true)}
							title="Naujas tiekėjas"
						>
							<Plus class="size-4" />
						</Button>
					</div>
				</div>
				<div class="grid grid-cols-3 gap-2">
					<div class="space-y-1.5">
						<Label>Dokumentas</Label>
						<Select.Root type="single" bind:value={docType}>
							<Select.Trigger class="w-full">{PURCHASE_DOC_KINDS[docType]}</Select.Trigger>
							<Select.Content>
								{#each Object.entries(PURCHASE_DOC_KINDS) as [v, label] (v)}
									<Select.Item value={v} {label}>{label}</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					</div>
					<div class="space-y-1.5">
						<Label>Dok. nr.</Label>
						<Input
							bind:value={docNumber}
							placeholder={docType === 'kio' ? 'Tuščia – KIO nr. auto' : 'Pvz. FV-2026-99'}
						/>
					</div>
					<div class="space-y-1.5">
						<Label>Dokumento data *</Label>
						<Input type="date" bind:value={documentDate} required />
					</div>
				</div>
			</div>

			<div class="grid gap-4 sm:grid-cols-2">
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-1.5">
						<Label>Valiuta</Label>
						<Select.Root
							type="single"
							bind:value={currency}
							onValueChange={() => {
								if (currency === 'EUR') exchangeRate = '1';
							}}
						>
							<Select.Trigger class="w-full">{currency}</Select.Trigger>
							<Select.Content>
								{#each CURRENCIES as c (c)}
									<Select.Item value={c} label={c}>{c}</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					</div>
					<div class="space-y-1.5">
						<Label>Kursas → EUR</Label>
						<Input
							type="number"
							step="0.000001"
							min="0"
							bind:value={exchangeRate}
							disabled={currency === 'EUR'}
							placeholder="Pvz. 0.2345"
						/>
					</div>
				</div>
				<div class="grid grid-cols-2 gap-2">
					<div class="space-y-1.5">
						<Label>Apmokėti iki</Label>
						<Input type="date" bind:value={dueDate} />
					</div>
					<div class="space-y-1.5">
						<Label>Kategorija</Label>
						<Select.Root type="single" bind:value={categoryId}>
							<Select.Trigger class="w-full">
								{categories.find((c) => String(c.id) === categoryId)?.name ?? '–'}
							</Select.Trigger>
							<Select.Content>
								<Select.Item value="" label="–">–</Select.Item>
								{#each categories as c (c.id)}
									<Select.Item value={String(c.id)} label={c.name}>{c.name}</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
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
								title="Nauja prekė/paslauga"
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
								placeholder="Kaina {currency}"
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

			{#if paidNow}
				<div class="grid gap-4 rounded-md border border-dashed p-3 sm:grid-cols-3">
					<div class="space-y-1.5">
						<Label>Mokėjimo būdas</Label>
						<Select.Root type="single" bind:value={paidMethod}>
							<Select.Trigger class="w-full">{PAYMENT_METHODS[paidMethod]}</Select.Trigger>
							<Select.Content>
								{#each Object.entries(PAYMENT_METHODS) as [v, label] (v)}
									<Select.Item value={v} {label}>{label}</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
					</div>
					<div class="space-y-1.5 sm:col-span-2">
						<Label>Mokėjimo dok. nr.</Label>
						<Input
							bind:value={paidDocNumber}
							placeholder={docType === 'kio'
								? 'Tuščia – KIO nr. suteikiamas automatiškai'
								: docType === 'sf'
									? 'Pvz. banko operacijos nr.'
									: 'Kvito/dokumento nr.'}
						/>
					</div>
				</div>
			{/if}

			<div class="space-y-1.5">
				<Label>Pastabos</Label>
				<Textarea bind:value={notes} rows={2} />
			</div>

			<div class="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
				<div class="flex flex-wrap items-center gap-4">
					<label class="flex items-center gap-2 text-sm">
						<input type="checkbox" bind:checked={deductible} /> Leidžiami atskaitymai
					</label>
					<label class="flex items-center gap-2 text-sm">
						<input type="checkbox" bind:checked={paidNow} /> Apmokėta iškart
					</label>
				</div>
				<span class="text-lg font-semibold">
					Iš viso: {fmtEur(totalEur)}{#if currency !== 'EUR'}
						<span class="text-sm font-normal text-muted-foreground">
							({total.toFixed(2)} {currency})</span
						>{/if}
				</span>
				<Button type="submit" disabled={saving || !supplierId}>
					{saving ? 'Saugoma…' : 'Išsaugoti pirkinį'}
				</Button>
			</div>
			{#if error}<p class="text-sm text-destructive">{error}</p>{/if}
		</Card.Content>
	</Card.Root>
</form>

<Dialog.Root bind:open={supplierDialog}>
	<Dialog.Content>
		<Dialog.Header><Dialog.Title>Naujas tiekėjas</Dialog.Title></Dialog.Header>
		<form onsubmit={createSupplier} class="space-y-3">
			<div class="space-y-1.5">
				<Label>Pavadinimas *</Label><Input bind:value={supplierForm.name} required />
			</div>
			<div class="grid grid-cols-2 gap-3">
				<div class="space-y-1.5"><Label>Kodas</Label><Input bind:value={supplierForm.code} /></div>
				<div class="space-y-1.5">
					<Label>PVM kodas</Label><Input bind:value={supplierForm.vat_code} />
				</div>
			</div>
			<div class="space-y-1.5">
				<Label>El. paštas</Label><Input type="email" bind:value={supplierForm.email} />
			</div>
			<Dialog.Footer><Button type="submit">Sukurti</Button></Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={serviceDialog}>
	<Dialog.Content>
		<Dialog.Header><Dialog.Title>Nauja prekė/paslauga (pirkimams)</Dialog.Title></Dialog.Header>
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
					<Label>Kaina *</Label><Input
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
