export interface Tenant {
	id: number;
	name: string;
	role: string;
}

export interface Me {
	id: number;
	username: string;
	email: string;
	tenants: Tenant[];
	current_tenant_id: number | null;
}

export interface Profile {
	seller_name: string;
	activity_code: string;
	personal_code: string;
	vat_code: string;
	address: string;
	bank_name: string;
	iban: string;
	email: string;
	phone: string;
	invoice_series: string;
	accounting_basis: 'cash' | 'accrual';
	deductions_method: 'pct30' | 'actual';
}

export interface Client {
	id: number;
	name: string;
	code: string;
	vat_code: string;
	email: string;
	address: string;
}

export interface InvoiceLine {
	id?: number;
	description: string;
	quantity: string;
	unit: string;
	unit_price: string;
	total?: string;
}

export interface Payment {
	id?: number;
	amount: string;
	paid_at: string;
	method: 'bank' | 'cash' | 'other';
	note: string;
}

export type InvoiceStatus = 'draft' | 'issued' | 'partially_paid' | 'paid' | 'cancelled';

export interface Invoice {
	id: number;
	client: Client;
	series: string;
	year: number | null;
	number: number | null;
	full_number: string | null;
	issue_date: string | null;
	due_date: string | null;
	currency: string;
	status: InvoiceStatus;
	notes: string;
	total: string;
	paid_total: string;
	lines: InvoiceLine[];
	payments: Payment[];
}

export interface Category {
	id: number;
	kind: 'income' | 'expense';
	name: string;
	is_deductible: boolean;
}

export interface LedgerEntry {
	id: number;
	kind: 'income' | 'expense';
	category_id: number | null;
	document_date: string;
	paid_date: string;
	counterparty: string;
	description: string;
	currency: 'EUR' | 'PLN';
	amount_original: string;
	exchange_rate: string;
	amount_eur: string;
	deductible: boolean;
}

export interface JournalRow {
	date: string;
	kind: string;
	description: string;
	counterparty: string;
	amount: string;
	deductible: boolean;
	source: string;
}

export interface Journal {
	rows: JournalRow[];
	income_total: string;
	expense_total: string;
	deductible_total: string;
	net: string;
}

export interface TaxLine {
	base: string;
	rate: string;
	amount: string;
	note: string;
}

export interface TaxBreakdown {
	year: number;
	income_total: string;
	expenses_total: string;
	deductible_total: string;
	deductions_method: string;
	deductions_applied: string;
	recommended_deductions_method: string;
	profit: string;
	gpm: TaxLine;
	vsd: TaxLine;
	psd: TaxLine;
	total: string;
	warnings: string[];
}

export interface SmtpSettings {
	host: string;
	port: number;
	username: string;
	from_email: string;
	from_name: string;
	use_tls: boolean;
	is_configured: boolean;
}

export interface RecurringTemplate {
	id: number;
	client: Client;
	series: string;
	frequency: 'monthly' | 'quarterly' | 'yearly';
	next_run_date: string;
	end_date: string | null;
	active: boolean;
	auto_send: boolean;
	email_to: string;
	notes: string;
	lines: InvoiceLine[];
}
