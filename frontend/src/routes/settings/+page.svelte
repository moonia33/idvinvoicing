<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api';
	import { auth } from '#lib/auth.svelte';
	import type { InvoiceSeries, Member, MemberRole, Profile, SmtpSettings } from '#lib/types';
	import { Star, Trash2 } from '@lucide/svelte';
	import { Button } from '#lib/components/ui/button';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import * as Select from '#lib/components/ui/select';
	import { Textarea } from '#lib/components/ui/textarea';
	import { Separator } from '#lib/components/ui/separator';

	let profile = $state<Profile>({
		seller_name: '',
		activity_code: '',
		personal_code: '',
		vat_code: '',
		address: '',
		bank_name: '',
		iban: '',
		email: '',
		phone: '',
		invoice_series: 'SF',
		accounting_basis: 'cash',
		deductions_method: 'pct30',
		insured_elsewhere: false,
		pension_accrual: false,
		vsd_holiday: false,
		sodra_exempt: false,
		activity_start: null as string | null
	});
	let smtp = $state({
		host: '',
		port: 587,
		username: '',
		password: '',
		from_email: '',
		from_name: '',
		use_tls: true
	});
	let profileMsg = $state('');
	let smtpMsg = $state('');
	let logoMsg = $state('');
	let seriesList = $state<InvoiceSeries[]>([]);
	let newSeries = $state('');
	let seriesMsg = $state('');

	async function addSeries(e: SubmitEvent) {
		e.preventDefault();
		seriesMsg = '';
		try {
			const s = await api<InvoiceSeries>('/invoice-series', {
				method: 'POST',
				body: { code: newSeries }
			});
			seriesList = [...seriesList, s];
			newSeries = '';
		} catch (err) {
			seriesMsg = err instanceof Error ? err.message : 'Klaida';
		}
	}

	async function setDefaultSeries(s: InvoiceSeries) {
		await api(`/invoice-series/${s.id}/set-default`, { method: 'POST' });
		seriesList = seriesList.map((x) => ({ ...x, is_default: x.id === s.id }));
	}

	async function removeSeries(s: InvoiceSeries) {
		if (!confirm(`Ištrinti seriją ${s.code}? Išrašytos sąskaitos nepakies.`)) return;
		try {
			await api(`/invoice-series/${s.id}`, { method: 'DELETE' });
			seriesList = seriesList.filter((x) => x.id !== s.id);
		} catch (err) {
			seriesMsg = err instanceof Error ? err.message : 'Klaida';
		}
	}

	async function uploadLogo(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		const fd = new FormData();
		fd.append('file', file);
		try {
			profile = await api<Profile>('/profile/logo', { method: 'POST', body: fd });
			logoMsg = 'Logotipas įkeltas.';
		} catch (err) {
			logoMsg = err instanceof Error ? err.message : 'Klaida įkeliant logotipą';
		}
		input.value = '';
	}

	async function removeLogo() {
		profile = await api<Profile>('/profile/logo', { method: 'DELETE' });
		logoMsg = 'Logotipas pašalintas.';
	}

	const BASIS: Record<string, string> = { cash: 'Pinigų principas', accrual: 'Kaupimo principas' };
	const DED: Record<string, string> = { pct30: '30% pajamų', actual: 'Faktinės išlaidos' };

	onMount(async () => {
		try {
			profile = await api<Profile>('/profile');
		} catch {
			// profilio dar nėra – paliekam tuščią formą
		}
		try {
			seriesList = await api<InvoiceSeries[]>('/invoice-series');
		} catch {
			seriesList = [];
		}
		loadMembers().catch(() => (members = []));
		const s = await api<SmtpSettings>('/mail/smtp');
		smtp = {
			...smtp,
			host: s.host,
			port: s.port,
			username: s.username,
			from_email: s.from_email,
			from_name: s.from_name,
			use_tls: s.use_tls
		};
	});

	async function saveProfile(e: SubmitEvent) {
		e.preventDefault();
		await api('/profile', { method: 'PUT', body: profile });
		profileMsg = 'Išsaugota.';
	}

	async function saveSmtp(e: SubmitEvent) {
		e.preventDefault();
		const body: Record<string, unknown> = { ...smtp };
		if (!smtp.password) delete body.password;
		await api('/mail/smtp', { method: 'PUT', body });
		smtpMsg = 'SMTP nustatymai išsaugoti.';
	}

	const ROLES: Record<MemberRole, string> = {
		owner: 'Savininkas',
		member: 'Narys',
		accountant: 'Buhalteris'
	};
	const ROLE_HINT: Record<MemberRole, string> = {
		owner: 'viskas, įskaitant narius ir nustatymus',
		member: 'sąskaitos, pirkimai, ataskaitos',
		accountant: 'tik peržiūra ir eksportai'
	};
	let isOwner = $derived(auth.currentTenant?.role === 'owner');
	let members = $state<Member[]>([]);
	let invite = $state<{ email: string; role: MemberRole }>({ email: '', role: 'member' });
	let membersMsg = $state('');

	async function loadMembers() {
		members = await api<Member[]>('/tenants/members');
	}

	async function inviteMember(e: SubmitEvent) {
		e.preventDefault();
		membersMsg = '';
		try {
			const m = await api<Member>('/tenants/members', { method: 'POST', body: invite });
			members = [...members, m];
			membersMsg = `Pakviesta: ${m.email}. Prisijungimo nuoroda išsiųsta laišku.`;
			invite = { email: '', role: 'member' };
		} catch (err) {
			membersMsg = err instanceof Error ? err.message : 'Klaida';
		}
	}

	async function changeRole(m: Member, role: MemberRole) {
		membersMsg = '';
		try {
			const upd = await api<Member>(`/tenants/members/${m.id}`, {
				method: 'PATCH',
				body: { role }
			});
			members = members.map((x) => (x.id === upd.id ? upd : x));
			if (m.user_id === auth.user?.id) await auth.load();
		} catch (err) {
			membersMsg = err instanceof Error ? err.message : 'Klaida';
			await loadMembers();
		}
	}

	async function removeMember(m: Member) {
		if (!confirm(`Pašalinti ${m.email || m.name} iš veiklos?`)) return;
		membersMsg = '';
		try {
			await api(`/tenants/members/${m.id}`, { method: 'DELETE' });
			members = members.filter((x) => x.id !== m.id);
		} catch (err) {
			membersMsg = err instanceof Error ? err.message : 'Klaida';
		}
	}
</script>

<h1 class="mb-6 text-2xl font-semibold">Nustatymai</h1>

<div class="grid gap-6 lg:grid-cols-2">
	<Card.Root>
		<Card.Header
			><Card.Title>Veiklos profilis</Card.Title><Card.Description
				>Rekvizitai sąskaitose</Card.Description
			></Card.Header
		>
		<form onsubmit={saveProfile}>
			<Card.Content class="space-y-3">
				<div class="space-y-1.5">
					<Label>Logotipas</Label>
					<div class="flex items-center gap-3">
						{#if profile.logo}
							<img
								src={profile.logo}
								alt="Veiklos logotipas"
								class="h-14 w-auto rounded border bg-white object-contain p-1"
							/>
							<Button type="button" variant="outline" size="sm" onclick={removeLogo}
								>Pašalinti</Button
							>
						{:else}
							<div
								class="flex h-14 w-24 items-center justify-center rounded border border-dashed text-xs text-muted-foreground"
							>
								Nėra
							</div>
						{/if}
						<label
							class="cursor-pointer rounded-md border border-input bg-secondary px-3 py-1.5 text-sm font-medium hover:bg-secondary/80"
						>
							Įkelti…
							<input type="file" accept="image/*" class="hidden" onchange={uploadLogo} />
						</label>
					</div>
					<p class="text-xs text-muted-foreground">
						PNG/JPG iki 3 MB – rodomas sąskaitų PDF ir šoninėje juostoje
					</p>
					{#if logoMsg}<p class="text-sm text-muted-foreground">{logoMsg}</p>{/if}
				</div>
				<div class="space-y-1.5">
					<Label>Pavadinimas / vardas *</Label><Input bind:value={profile.seller_name} required />
				</div>
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1.5">
						<Label>IV kodas</Label><Input bind:value={profile.activity_code} />
					</div>
					<div class="space-y-1.5">
						<Label>Asmens kodas</Label><Input bind:value={profile.personal_code} />
					</div>
				</div>
				<div class="space-y-1.5">
					<Label>Adresas</Label><Textarea bind:value={profile.address} rows={2} />
				</div>
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1.5">
						<Label>Bankas</Label><Input bind:value={profile.bank_name} />
					</div>
					<div class="space-y-1.5"><Label>IBAN</Label><Input bind:value={profile.iban} /></div>
				</div>
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1.5">
						<Label>El. paštas</Label><Input type="email" bind:value={profile.email} />
					</div>
					<div class="space-y-1.5">
						<Label>Telefonas</Label><Input bind:value={profile.phone} />
					</div>
				</div>
				<Separator />
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1.5">
						<Label>Apskaita</Label>
						<Select.Root type="single" bind:value={profile.accounting_basis}>
							<Select.Trigger>{BASIS[profile.accounting_basis]}</Select.Trigger>
							<Select.Content>
								{#each Object.entries(BASIS) as [v, l] (v)}<Select.Item value={v} label={l}
										>{l}</Select.Item
									>{/each}
							</Select.Content>
						</Select.Root>
					</div>
					<div class="space-y-1.5">
						<Label>Atskaitymai</Label>
						<Select.Root type="single" bind:value={profile.deductions_method}>
							<Select.Trigger>{DED[profile.deductions_method]}</Select.Trigger>
							<Select.Content>
								{#each Object.entries(DED) as [v, l] (v)}<Select.Item value={v} label={l}
										>{l}</Select.Item
									>{/each}
							</Select.Content>
						</Select.Root>
					</div>
				</div>
				<div class="max-w-xs space-y-1.5">
					<Label>Veiklos pradžios data</Label>
					<Input type="date" bind:value={profile.activity_start} />
					<p class="text-xs text-muted-foreground">
						Nuo jos pradedama skaičiuoti minimali VSD/PSD bazė (MMA × veiklos mėn.)
					</p>
				</div>
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={profile.insured_elsewhere} />
					Dirbu pagal darbo sutartį (draustas kitur – be MMA minimumo, bet metų gale VSD/PSD nuo 90 %
					apmokestinamųjų pajamų vis tiek skaičiuojami)
				</label>
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={profile.pension_accrual} />
					Papildomai kaupiu pensijai (VSD tarifas 15,52 % vietoj 12,52 %)
				</label>
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={profile.vsd_holiday} />
					Pirmoji individuali veikla – VSD atostogos (nemokama iki 12 mėn. nuo veiklos pradžios)
				</label>
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={profile.sodra_exempt} />
					Pensininkas / draustas valstybės lėšomis – VSD ir PSD visiškai nemokami
				</label>
				{#if profileMsg}<p class="text-sm text-green-600">{profileMsg}</p>{/if}
			</Card.Content>
			<Card.Footer><Button type="submit">Išsaugoti profilį</Button></Card.Footer>
		</form>
	</Card.Root>

	<Card.Root>
		<Card.Header
			><Card.Title>Sąskaitų serijos</Card.Title><Card.Description
				>Viena numatytoji + papildomos serijos (pvz. „SFK" – atgalinėms datoms ar korekcijoms;
				kiekviena turi atskirą numeraciją)</Card.Description
			></Card.Header
		>
		<Card.Content class="space-y-3">
			{#each seriesList as s (s.id)}
				<div class="flex items-center justify-between border-b pb-2 text-sm last:border-0">
					<span class="font-medium">
						{s.code}
						{#if s.is_default}
							<span class="ml-1 text-xs text-muted-foreground">(numatytoji)</span>
						{/if}
					</span>
					<span class="flex items-center gap-1">
						{#if !s.is_default}
							<Button
								variant="ghost"
								size="sm"
								class="h-7 px-2 text-xs"
								onclick={() => setDefaultSeries(s)}
								><Star class="size-3.5" /> Padaryti numatytąja</Button
							>
							<Button
								variant="ghost"
								size="icon"
								class="h-7 w-7 text-destructive"
								onclick={() => removeSeries(s)}><Trash2 class="size-3.5" /></Button
							>
						{/if}
					</span>
				</div>
			{/each}
			<form onsubmit={addSeries} class="flex items-end gap-2 pt-1">
				<div class="w-40 space-y-1.5">
					<Label>Nauja serija</Label>
					<Input bind:value={newSeries} placeholder="Pvz. SFK" maxlength={10} required />
				</div>
				<Button type="submit" variant="outline">Pridėti</Button>
			</form>
			{#if seriesMsg}<p class="text-sm text-destructive">{seriesMsg}</p>{/if}
		</Card.Content>
	</Card.Root>

	<Card.Root>
		<Card.Header
			><Card.Title>SMTP (el. pašto siuntimas)</Card.Title><Card.Description
				>Naudojama sąskaitų siuntimui</Card.Description
			></Card.Header
		>
		<form onsubmit={saveSmtp}>
			<Card.Content class="space-y-3">
				<div class="grid grid-cols-3 gap-3">
					<div class="col-span-2 space-y-1.5">
						<Label>Serveris *</Label><Input
							bind:value={smtp.host}
							required
							placeholder="smtp.gmail.com"
						/>
					</div>
					<div class="space-y-1.5">
						<Label>Portas</Label><Input type="number" bind:value={smtp.port} />
					</div>
				</div>
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1.5">
						<Label>Vartotojas</Label><Input bind:value={smtp.username} />
					</div>
					<div class="space-y-1.5">
						<Label>Slaptažodis</Label><Input
							type="password"
							bind:value={smtp.password}
							placeholder="(palikti tuščią – nekeisti)"
							autocomplete="new-password"
						/>
					</div>
				</div>
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1.5">
						<Label>Siuntėjo el. paštas</Label><Input type="email" bind:value={smtp.from_email} />
					</div>
					<div class="space-y-1.5">
						<Label>Siuntėjo vardas</Label><Input bind:value={smtp.from_name} />
					</div>
				</div>
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={smtp.use_tls} /> Naudoti TLS
				</label>
				{#if smtpMsg}<p class="text-sm text-green-600">{smtpMsg}</p>{/if}
			</Card.Content>
			<Card.Footer><Button type="submit">Išsaugoti SMTP</Button></Card.Footer>
		</form>
	</Card.Root>

	<Card.Root>
		<Card.Header
			><Card.Title>Paskyra</Card.Title><Card.Description>Prisijungimo duomenys</Card.Description
			></Card.Header
		>
		<Card.Content class="space-y-3">
			<div class="grid grid-cols-2 gap-3 text-sm">
				<div>
					<div class="text-muted-foreground">Vartotojas</div>
					<div class="font-medium">{auth.user?.username ?? '—'}</div>
				</div>
				<div>
					<div class="text-muted-foreground">El. paštas</div>
					<div class="font-medium">{auth.user?.email || '—'}</div>
				</div>
			</div>
			<p class="text-xs text-muted-foreground">
				Prisijungiama tik vienkartiniu kodu, siunčiamu šiuo el. paštu. Slaptažodžių nėra. El. paštą
				gali keisti administratorius (/admin).
			</p>
		</Card.Content>
	</Card.Root>

	<Card.Root class="lg:col-span-2">
		<Card.Header
			><Card.Title>Veiklos nariai</Card.Title><Card.Description
				>Kas gali tvarkyti veiklą „{auth.currentTenant?.name}“</Card.Description
			></Card.Header
		>
		<Card.Content class="space-y-4">
			<div class="divide-y rounded-md border">
				{#each members as m (m.id)}
					<div class="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
						<div class="min-w-0 flex-1">
							<div class="truncate font-medium">{m.email || m.name}</div>
							<div class="text-xs text-muted-foreground">{ROLE_HINT[m.role]}</div>
						</div>
						{#if isOwner}
							<select
								class="h-9 rounded-md border bg-background px-2 text-sm"
								aria-label="Rolė"
								value={m.role}
								onchange={(e) => changeRole(m, e.currentTarget.value as MemberRole)}
							>
								{#each Object.entries(ROLES) as [v, l] (v)}<option value={v}>{l}</option>{/each}
							</select>
							<Button
								variant="ghost"
								size="icon"
								aria-label="Pašalinti narį"
								onclick={() => removeMember(m)}><Trash2 class="size-4" /></Button
							>
						{:else}
							<span class="text-muted-foreground">{ROLES[m.role]}</span>
						{/if}
					</div>
				{/each}
			</div>
			{#if isOwner}
				<Separator />
				<form onsubmit={inviteMember} class="flex flex-wrap items-end gap-3">
					<div class="min-w-56 flex-1 space-y-1.5">
						<Label for="invite-email">Pakviesti pagal el. paštą</Label>
						<Input id="invite-email" type="email" bind:value={invite.email} required />
					</div>
					<div class="space-y-1.5">
						<Label for="invite-role">Rolė</Label>
						<select
							id="invite-role"
							class="h-9 rounded-md border bg-background px-2 text-sm"
							bind:value={invite.role}
						>
							{#each Object.entries(ROLES) as [v, l] (v)}<option value={v}>{l}</option>{/each}
						</select>
					</div>
					<Button type="submit">Pakviesti</Button>
				</form>
				<p class="text-xs text-muted-foreground">
					Jei vartotojo dar nėra, jis sukuriamas be slaptažodžio ir gauna kvietimo laišką.
					Prisijungs kodu el. paštu.
				</p>
			{/if}
			{#if membersMsg}
				<p class="text-sm {membersMsg.startsWith('Pakviesta') ? 'text-green-600' : 'text-red-600'}">
					{membersMsg}
				</p>
			{/if}
		</Card.Content>
	</Card.Root>
</div>
