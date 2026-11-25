<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { auth } from '#lib/auth.svelte';
	import { ApiError } from '#lib/api';
	import { Button } from '#lib/components/ui/button';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';

	let email = $state('');
	let code = $state('');
	let step = $state<'email' | 'code'>('email');
	let error = $state('');
	let info = $state('');
	let loading = $state(false);

	async function sendCode(e?: SubmitEvent) {
		e?.preventDefault();
		error = '';
		loading = true;
		try {
			await auth.requestCode(email.trim());
			step = 'code';
			code = '';
			info = `Jei ${email.trim()} registruotas, išsiuntėme 6 skaitmenų kodą. Jis galioja 10 min.`;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Kodo išsiųsti nepavyko';
		} finally {
			loading = false;
		}
	}

	async function verify(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		loading = true;
		try {
			await auth.verifyCode(email.trim(), code.trim());
			goto(auth.currentTenant ? resolve('/') : resolve('/select-tenant'));
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Prisijungti nepavyko';
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-muted/40">
	<Card.Root class="w-full max-w-sm">
		<Card.Header>
			<Card.Title class="text-xl">IDV Apskaita</Card.Title>
			<Card.Description>
				{step === 'email'
					? 'Įveskite el. paštą – atsiųsime prisijungimo kodą'
					: 'Įveskite kodą iš laiško'}
			</Card.Description>
		</Card.Header>
		{#if step === 'email'}
			<form onsubmit={sendCode}>
				<Card.Content class="space-y-4">
					<div class="space-y-1.5">
						<Label for="email">El. paštas</Label>
						<Input id="email" type="email" bind:value={email} autocomplete="email" required />
					</div>
					{#if error}
						<p class="text-sm text-destructive">{error}</p>
					{/if}
				</Card.Content>
				<Card.Footer>
					<Button type="submit" class="w-full" disabled={loading}>
						{loading ? 'Siunčiama…' : 'Gauti kodą'}
					</Button>
				</Card.Footer>
			</form>
		{:else}
			<form onsubmit={verify}>
				<Card.Content class="space-y-4">
					<p class="text-sm text-muted-foreground">{info}</p>
					<div class="space-y-1.5">
						<Label for="code">Kodas</Label>
						<Input
							id="code"
							bind:value={code}
							inputmode="numeric"
							autocomplete="one-time-code"
							pattern={'[0-9]{6}'}
							maxlength={6}
							required
						/>
					</div>
					{#if error}
						<p class="text-sm text-destructive">{error}</p>
					{/if}
				</Card.Content>
				<Card.Footer class="flex flex-col gap-2">
					<Button type="submit" class="w-full" disabled={loading}>
						{loading ? 'Jungiamasi…' : 'Prisijungti'}
					</Button>
					<div class="flex w-full justify-between text-sm">
						<button
							type="button"
							class="text-muted-foreground hover:underline"
							onclick={() => {
								step = 'email';
								error = '';
							}}>Kitas el. paštas</button
						>
						<button
							type="button"
							class="text-muted-foreground hover:underline"
							disabled={loading}
							onclick={() => sendCode()}>Siųsti iš naujo</button
						>
					</div>
				</Card.Footer>
			</form>
		{/if}
	</Card.Root>
</div>
