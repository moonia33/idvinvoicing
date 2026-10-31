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
	insured_elsewhere: boolean;
	pension_accrual: boolean;
	vsd_holiday: boolean;
	activity_start: string | null;
}

export interface Contact {
	id: number;
	name: string;
	code: string;
	vat_code: string;
	email: string;
	address: string;
	is_client: boolean;
	is_supplier: boolean;
}

export interface InvoiceLine {
	id?: number;
	description: string;
	quantity: string;
	unit: string;
	unit_price: string;
	total?: string;
}

export type PaymentMethod = 'bank' | 'cash' | 'card' | 'other';
export type PaymentDocType = '' | 'kpo' | 'ppk';

export interface Payment {
	id?: number;
	amount: string;
	paid_at: string;
	method: PaymentMethod;
	doc_type: PaymentDocType;
	doc_number: string;
	note: string;
}

export type InvoiceStatus = 'draft' | 'issued' | 'partially_paid' | 'paid' | 'cancelled';

export interface Service {
	id: number;
	code: string;
	name: string;
	category_id: number | null;
	unit: string;
	unit_price: string;
	is_sale: boolean;
	is_purchase: boolean;
	active: boolean;
}

export interface Invoice {
	id: number;
	client: Contact;
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

export type PurchaseDocType = '' | 'kio' | 'ppk';
export type PurchaseStatus = 'received' | 'partially_paid' | 'paid' | 'cancelled';

export interface PurchaseLine {
	id?: number;
	description: string;
	quantity: string;
	unit: string;
	unit_price: string;
	total?: string;
}

export interface PurchasePayment {
	id?: number;
	amount_original: string;
	exchange_rate: string;
	amount_eur?: string;
	paid_at: string;
	method: PaymentMethod;
	doc_type: PurchaseDocType;
	doc_number: string;
	note: string;
}

export interface Purchase {
	id: number;
	supplier: Contact;
	doc_number: string;
	document_date: string;
	due_date: string | null;
	currency: 'EUR' | 'PLN';
	exchange_rate: string;
	status: PurchaseStatus;
	category_id: number | null;
	deductible: boolean;
	notes: string;
	total: string;
	total_eur: string;
	paid_total: string;
	lines: PurchaseLine[];
	payments: PurchasePayment[];
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
	tax_kind: '' | 'gpm' | 'vsd' | 'psd';
	tax_year: number | null;
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
	paid: string;
	remaining: string;
}

export interface MonthRow {
	month: number;
	income: string;
	profit: string;
	vsd: string;
	psd: string;
}

export interface TaxBreakdown {
	year: number;
	months: number;
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
	paid_total: string;
	remaining_total: string;
	monthly: MonthRow[];
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
	client: Contact;
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
