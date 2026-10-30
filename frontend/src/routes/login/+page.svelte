<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { auth } from '#lib/auth.svelte';
	import { ApiError } from '#lib/api';
	import { Button } from '#lib/components/ui/button';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';

	let username = $state('');
	let password = $state('');
	let error = $state('');
	let loading = $state(false);

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		loading = true;
		try {
			await auth.login(username, password);
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
			<Card.Description>Prisijunkite prie individualios veiklos apskaitos</Card.Description>
		</Card.Header>
		<form onsubmit={submit}>
			<Card.Content class="space-y-4">
				<div class="space-y-1.5">
					<Label for="username">Vartotojas</Label>
					<Input id="username" bind:value={username} autocomplete="username" required />
				</div>
				<div class="space-y-1.5">
					<Label for="password">Slaptažodis</Label>
					<Input
						id="password"
						type="password"
						bind:value={password}
						autocomplete="current-password"
						required
					/>
				</div>
				{#if error}
					<p class="text-sm text-destructive">{error}</p>
				{/if}
			</Card.Content>
			<Card.Footer>
				<Button type="submit" class="w-full" disabled={loading}>
					{loading ? 'Jungiamasi…' : 'Prisijungti'}
				</Button>
			</Card.Footer>
		</form>
	</Card.Root>
</div>
