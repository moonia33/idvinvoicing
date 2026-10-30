import { api, ensureCsrf } from './api';
import type { Me, Tenant } from './types';

class Auth {
	user = $state<Me | null>(null);
	loaded = $state(false);

	get tenants(): Tenant[] {
		return this.user?.tenants ?? [];
	}

	get currentTenant(): Tenant | null {
		if (!this.user) return null;
		return this.tenants.find((t) => t.id === this.user!.current_tenant_id) ?? null;
	}

	async load(): Promise<Me | null> {
		try {
			this.user = await api<Me>('/auth/me');
		} catch {
			this.user = null;
		} finally {
			this.loaded = true;
		}
		return this.user;
	}

	async login(username: string, password: string): Promise<void> {
		await ensureCsrf();
		this.user = await api<Me>('/auth/login', {
			method: 'POST',
			body: { username, password }
		});
		this.loaded = true;
	}

	async logout(): Promise<void> {
		await api('/auth/logout', { method: 'POST' });
		this.user = null;
	}

	async switchTenant(tenantId: number): Promise<void> {
		await api('/tenants/switch', { method: 'POST', body: { tenant_id: tenantId } });
		await this.load();
	}

	async createTenant(name: string): Promise<void> {
		await api('/tenants', { method: 'POST', body: { name } });
		await this.load();
	}
}

export const auth = new Auth();
