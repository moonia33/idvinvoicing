import { describe, expect, it } from 'vitest';
import { fmtEur, fmtDate, STATUS_LABELS } from './format';

describe('fmtEur', () => {
	it('formatuoja decimal string kaip EUR', () => {
		expect(fmtEur('1234.50')).toContain('1234');
		expect(fmtEur('0')).toBeTruthy();
	});
});

describe('fmtDate', () => {
	it('grąžina – kai null', () => {
		expect(fmtDate(null)).toBe('–');
	});
	it('grąžina datą', () => {
		expect(fmtDate('2026-01-15')).toBe('2026-01-15');
	});
});

describe('STATUS_LABELS', () => {
	it('turi visus sąskaitos statusus', () => {
		for (const s of ['draft', 'issued', 'partially_paid', 'paid', 'cancelled']) {
			expect(STATUS_LABELS[s]).toBeTruthy();
		}
	});
});
