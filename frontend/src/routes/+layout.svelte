<script lang="ts">
	import './layout.css';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import favicon from '#lib/assets/favicon.svg';
	import { auth } from '#lib/auth.svelte';
	import { cn } from '#lib/utils.js';
	import { Button } from '#lib/components/ui/button';
	import * as Select from '#lib/components/ui/select';
	import {
		LayoutDashboard,
		FileText,
		Users,
		BookOpen,
		Repeat,
		Calculator,
		Settings,
		LogOut,
		Package,
		ShoppingCart,
		Truck
	} from '@lucide/svelte';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	const NAV = [
		{ href: '/', label: 'Suvestinė', icon: LayoutDashboard },
		{ href: '/invoices', label: 'Sąskaitos', icon: FileText },
		{ href: '/services', label: 'Paslaugos', icon: Package },
		{ href: '/clients', label: 'Klientai', icon: Users },
		{ href: '/purchases', label: 'Pirkimai', icon: ShoppingCart },
		{ href: '/suppliers', label: 'Tiekėjai', icon: Truck },
		{ href: '/journal', label: 'Žurnalas', icon: BookOpen },
		{ href: '/recurring', label: 'Pasikartojančios', icon: Repeat },
		{ href: '/taxes', label: 'Mokesčiai', icon: Calculator },
		{ href: '/settings', label: 'Nustatymai', icon: Settings }
	];

	const PUBLIC_PATHS = ['/login', '/select-tenant'];

	onMount(() => {
		auth.load();
	});

	$effect(() => {
		if (!auth.loaded) return;
		const path = page.url.pathname;
		if (!auth.user && path !== '/login') {
			goto(resolve('/login'));
		} else if (auth.user && !auth.user.current_tenant_id && path !== '/select-tenant') {
			goto(resolve('/select-tenant'));
		}
	});

	async function onTenantChange(v: string | undefined) {
		if (v) await auth.switchTenant(Number(v));
	}
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>IDV Apskaita</title>
</svelte:head>

{#if !auth.loaded}
	<div class="flex h-screen items-center justify-center text-muted-foreground">Kraunama…</div>
{:else if !auth.user || (!auth.currentTenant && page.url.pathname !== '/select-tenant') || PUBLIC_PATHS.includes(page.url.pathname)}
	{@render children()}
{:else}
	<div class="flex min-h-screen">
		<aside class="flex w-60 flex-col border-r bg-muted/30">
			<div class="px-4 py-4 text-lg font-semibold">IDV Apskaita</div>
			<nav class="flex-1 space-y-0.5 px-2">
				{#each NAV as item (item.href)}
					{@const Icon = item.icon}
					<a
						href={resolve(item.href as '/')}
						class={cn(
							'flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted',
							page.url.pathname === item.href && 'bg-muted font-medium'
						)}
					>
						<Icon class="size-4" />
						{item.label}
					</a>
				{/each}
			</nav>
			<div class="space-y-2 border-t p-3">
				<Select.Root
					type="single"
					value={String(auth.currentTenant?.id ?? '')}
					onValueChange={onTenantChange}
				>
					<Select.Trigger class="w-full">{auth.currentTenant?.name}</Select.Trigger>
					<Select.Content>
						{#each auth.tenants as t (t.id)}
							<Select.Item value={String(t.id)} label={t.name}>{t.name}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
				<Button variant="ghost" class="w-full justify-start" onclick={() => auth.logout()}>
					<LogOut class="size-4" /> Atsijungti
				</Button>
			</div>
		</aside>
		<main class="flex-1 overflow-auto p-6">{@render children()}</main>
	</div>
{/if}
