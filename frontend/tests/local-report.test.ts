import { describe, expect, it } from 'vitest';
import { makePublicSummary, MAX_REPORT_BYTES, parseLocalReport } from '../src/reports/localReport';
import { report, scan } from './fixtures';

function completeInput() { return { ...structuredClone(report), engines: Object.entries(scan.stages).map(([name, stage]) => ({ name, version: '1.0', ...stage })) }; }

describe('local JSON report boundary', () => {
  it('retains unmeasured nulls and reads a real complete report shape', () => {
    const document = parseLocalReport(JSON.stringify(completeInput()));
    expect(document.mode).toBe('full');
    expect(document.report.quality.score).toBeNull();
    expect(document.report.quality.coverage).toBe(0.4);
    expect(document.scan.stages.dynamic.status).toBe('UNAVAILABLE');
  });
  it('rejects inconsistent counts and fabricated full quality', () => {
    const source = completeInput(); source.security.finding_counts.high = 20;
    expect(() => parseLocalReport(JSON.stringify(source))).toThrow(/不一致/);
    const forged = completeInput(); forged.quality.score = 99;
    expect(() => parseLocalReport(JSON.stringify(forged))).toThrow(/不一致/);
  });
  it('bounds bytes, nested structures and prototype-like properties', () => {
    expect(() => parseLocalReport(' '.repeat(MAX_REPORT_BYTES + 1))).toThrow(/5 MiB/);
    expect(() => parseLocalReport('{"__proto__":{"x":1},"schema_version":"1.0"}')).toThrow();
    expect(() => parseLocalReport('['.repeat(25) + '0' + ']'.repeat(25))).toThrow();
    expect(() => parseLocalReport('{"schema_version":"1.0","value":1e999}')).toThrow();
  });
  it('does not copy free text or identifiers to a public summary', () => {
    const source = completeInput();
    source.artifact.name = 'private-customer-name';
    source.security.findings[0].file_path = 'private-path/secret-customer.py';
    source.security.findings[0].evidence_excerpt = 'MY_TOKEN = "SyntheticSecret123456789"';
    source.engines[0].reason = 'private-stage-reason';
    const summary = makePublicSummary(parseLocalReport(JSON.stringify(source)));
    const json = JSON.stringify(summary);
    expect(json).not.toContain('private-customer'); expect(json).not.toContain('private-path');
    expect(json).not.toContain('SyntheticSecret'); expect(json).not.toContain('private-stage-reason');
    expect(json).not.toContain('fingerprint'); expect(json).not.toContain('sha256');
    expect(summary.severity_counts.high).toBe(1);
    const reimported = parseLocalReport(json);
    expect(reimported.mode).toBe('aggregate');
    expect(reimported.report.security.findings).toEqual([]);
    expect(reimported.report.security.finding_counts.high).toBe(1);
    expect(reimported.report.quality.score).toBeNull();
  });
  it('rejects inconsistent aggregate counts and maps unknown categories to other', () => {
    const source = completeInput(); source.security.findings[0].category = 'private-business-category';
    const summary = makePublicSummary(parseLocalReport(JSON.stringify(source)));
    expect(summary.category_counts).toEqual({ other: 1 });
    expect(JSON.stringify(summary)).not.toContain('private-business-category');
    summary.rule_counts = {};
    expect(() => parseLocalReport(JSON.stringify(summary))).toThrow();
  });
});
