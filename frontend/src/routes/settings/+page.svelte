<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '#lib/api';
	import type { Profile, SmtpSettings } from '#lib/types';
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
		vsd_holiday: false
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

	const BASIS: Record<string, string> = { cash: 'Pinigų principas', accrual: 'Kaupimo principas' };
	const DED: Record<string, string> = { pct30: '30% pajamų', actual: 'Faktinės išlaidos' };

	onMount(async () => {
		try {
			profile = await api<Profile>('/profile');
		} catch {
			// profilio dar nėra – paliekam tuščią formą
		}
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
				<div class="grid grid-cols-3 gap-3">
					<div class="space-y-1.5">
						<Label>Sąskaitų serija</Label><Input bind:value={profile.invoice_series} />
					</div>
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
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={profile.insured_elsewhere} />
					Dirbu pagal darbo sutartį (draustas kitur – be MMA minimumo, bet metų gale VSD/PSD nuo 90 %
					pelno vis tiek skaičiuojami)
				</label>
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={profile.pension_accrual} />
					Papildomai kaupiu pensijai (VSD tarifas 15,52 % vietoj 12,52 %)
				</label>
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={profile.vsd_holiday} />
					Pirmoji individuali veikla – VSD atostogos (nemokama iki 12 mėn. nuo veiklos pradžios)
				</label>
				{#if profileMsg}<p class="text-sm text-green-600">{profileMsg}</p>{/if}
			</Card.Content>
			<Card.Footer><Button type="submit">Išsaugoti profilį</Button></Card.Footer>
		</form>
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
</div>
