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

export type MemberRole = 'owner' | 'member' | 'accountant';

export interface Member {
	id: number;
	user_id: number;
	email: string;
	name: string;
	role: MemberRole;
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
	sodra_exempt: boolean;
	activity_start: string | null;
	logo?: string;
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
export type PaymentDocType = '' | 'kpo' | 'ppk' | 'receipt';

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

export interface InvoiceSeries {
	id: number;
	code: string;
	is_default: boolean;
}

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

export type PurchaseDocType = '' | 'kio' | 'ppk' | 'receipt';
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

export type PurchaseDocKind = 'sf' | 'receipt' | 'ppk' | 'kio';

export interface Purchase {
	id: number;
	supplier: Contact;
	doc_type: PurchaseDocKind;
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
	taxable_income: string;
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
	taxable_income: string;
	net_earning: string;
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

export type TransferDirection = 'in' | 'out';
export type TransferStatus = 'unallocated' | 'partial' | 'allocated' | 'ignored';

export interface TransferAllocation {
	id: number;
	kind: 'invoice' | 'purchase';
	document_id: number;
	document_label: string;
	amount: string;
	doc_type: string;
	doc_number: string;
}

export interface Transfer {
	id: number;
	direction: TransferDirection;
	date: string;
	amount: string;
	currency: string;
	method: PaymentMethod;
	counterparty_id: number | null;
	counterparty_display: string;
	counterparty_name: string;
	counterparty_iban: string;
	reference: string;
	note: string;
	ignored: boolean;
	doc_type: string;
	doc_number: string;
	account_iban: string;
	bank_import_id: number | null;
	source: 'manual' | 'import';
	status: TransferStatus;
	allocated_total: string;
	unallocated: string;
	allocations: TransferAllocation[];
}

export interface OpenDocument {
	kind: 'invoice' | 'purchase';
	id: number;
	label: string;
	counterparty_id: number;
	counterparty_name: string;
	date: string;
	due_date: string | null;
	currency: string;
	total: string;
	remaining: string;
}

export interface ImportStatement {
	account_iban: string;
	currency: string;
	bank_name: string;
	owner_name: string;
	period_from: string | null;
	period_to: string | null;
	entries: number;
	skipped: number;
}

export interface ImportEntry {
	account_iban: string;
	external_id: string;
	direction: TransferDirection;
	date: string;
	amount: string;
	currency: string;
	method: PaymentMethod;
	counterparty_name: string;
	counterparty_iban: string;
	counterparty_code: string;
	counterparty_id: number | null;
	reference: string;
	bank_code: string;
	own_transfer: boolean;
	duplicate: boolean;
	supported: boolean;
}

export interface ImportResult {
	statements: ImportStatement[];
	entries: ImportEntry[];
	new_count: number;
	duplicate_count: number;
	unsupported_count: number;
	created_count: number;
}
