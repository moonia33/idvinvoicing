import { describe, expect, it } from 'vitest';
import { autoAllocate, fromCents, queryString, toCents } from './allocate';

describe('autoAllocate', () => {
	it('dengia nuo seniausio, likutį palieka', () => {
		expect(autoAllocate('150', ['100.00', '80.00', '10'])).toEqual(['100.00', '50.00', '']);
	});
	it('permoka nepaskirstoma', () => {
		expect(autoAllocate('200', ['100.00', '80.00'])).toEqual(['100.00', '80.00']);
	});
	it('nulinė suma', () => {
		expect(autoAllocate('', ['10'])).toEqual(['']);
	});
	it('be slankaus kablelio paklaidų', () => {
		expect(autoAllocate('0.3', ['0.1', '0.2'])).toEqual(['0.10', '0.20']);
		expect(fromCents(toCents('19.99') + toCents('0.01'))).toBe('20.00');
	});
});

describe('queryString', () => {
	it('praleidžia tuščias reikšmes ir koduoja', () => {
		expect(queryString({ a: 'x y', b: '', c: null, d: 2 })).toBe('?a=x%20y&d=2');
		expect(queryString({ a: '' })).toBe('');
	});
});
