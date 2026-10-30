export const fmtEur = (v: string | number): string =>
	new Intl.NumberFormat('lt-LT', { style: 'currency', currency: 'EUR' }).format(Number(v));

export const fmtDate = (d: string | null): string => d ?? '–';

export const STATUS_LABELS: Record<string, string> = {
	draft: 'Juodraštis',
	issued: 'Išrašyta',
	partially_paid: 'Dalinai apmokėta',
	paid: 'Apmokėta',
	cancelled: 'Anuliuota'
};

export const STATUS_VARIANTS: Record<string, 'secondary' | 'default' | 'outline' | 'destructive'> =
	{
		draft: 'secondary',
		issued: 'default',
		partially_paid: 'outline',
		paid: 'outline',
		cancelled: 'destructive'
	};

export const FREQ_LABELS: Record<string, string> = {
	monthly: 'Kas mėnesį',
	quarterly: 'Kas ketvirtį',
	yearly: 'Kasmet'
};
