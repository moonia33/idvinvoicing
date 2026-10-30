<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { auth } from '#lib/auth.svelte';
	import { Button } from '#lib/components/ui/button';
	import { Input } from '#lib/components/ui/input';
	import { Label } from '#lib/components/ui/label';
	import * as Card from '#lib/components/ui/card';
	import { Separator } from '#lib/components/ui/separator';

	let newName = $state('');
	let loading = $state(false);

	async function pick(id: number) {
		loading = true;
		await auth.switchTenant(id);
		goto(resolve('/'));
	}

	async function create(e: SubmitEvent) {
		e.preventDefault();
		loading = true;
		await auth.createTenant(newName);
		goto(resolve('/'));
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-muted/40">
	<Card.Root class="w-full max-w-md">
		<Card.Header>
			<Card.Title>Pasirinkite veiklą</Card.Title>
			<Card.Description>Kiekviena veikla turi atskirą apskaitą</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-4">
			{#if auth.tenants.length > 0}
				<div class="space-y-2">
					{#each auth.tenants as t (t.id)}
						<Button variant="outline" class="w-full justify-start" onclick={() => pick(t.id)}>
							{t.name}
							<span class="ml-auto text-xs text-muted-foreground">{t.role}</span>
						</Button>
					{/each}
				</div>
				<Separator />
			{/if}
			<form onsubmit={create} class="space-y-3">
				<Label for="name">Nauja veikla</Label>
				<Input id="name" bind:value={newName} placeholder="Veiklos pavadinimas" required />
				<Button type="submit" class="w-full" disabled={loading || !newName}>Sukurti</Button>
			</form>
		</Card.Content>
	</Card.Root>
</div>
