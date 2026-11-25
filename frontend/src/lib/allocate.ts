/** Suma centais, kad nebūtų slankaus kablelio paklaidų. */
export const toCents = (v: string | number): number => Math.round(Number(v || 0) * 100);
export const fromCents = (c: number): string => (c / 100).toFixed(2);

/**
 * Paskirsto mokėjimo sumą dokumentams nuo seniausio (dokumentai jau surikiuoti).
 * Grąžina sumas tuo pačiu eiliškumu; neužpildyti dokumentai gauna ''.
 */
export function autoAllocate(amount: string | number, remaining: (string | number)[]): string[] {
	let left = toCents(amount);
	return remaining.map((r) => {
		const take = Math.max(0, Math.min(left, toCents(r)));
		left -= take;
		return take > 0 ? fromCents(take) : '';
	});
}

/** Užklausos eilutė be tuščių reikšmių: `?a=1&b=2` arba ''. */
export function queryString(params: Record<string, string | number | null | undefined>): string {
	const pairs = Object.entries(params)
		.filter(([, v]) => v !== '' && v !== null && v !== undefined)
		.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
	return pairs.length ? `?${pairs.join('&')}` : '';
}
