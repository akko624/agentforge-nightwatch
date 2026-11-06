import { describe, expect, it, vi } from 'vitest';
import { makePublicSummary, parseLocalReport } from '../src/reports/localReport';
import { report, scan } from './fixtures';

function completeInput() {
  return { ...structuredClone(report), engines: Object.entries(scan.stages).map(([name, stage]) => ({ name, version: '1.0', ...stage })) };
}

describe('independent review of public report integrity', () => {
  it('rejects a static subscore when neither static dimension has been measured', () => {
    const source = completeInput();
    source.quality.coverage = 0;
    source.quality.static_subscore = 99;
    source.quality.dimensions = source.quality.dimensions.map((dimension) => ({ ...dimension, status: 'NOT_RUN', score: null }));
    expect(() => parseLocalReport(JSON.stringify(source))).toThrow();
  });

  it('does not invent a zero duration for an aggregate completed stage missing its measurement', () => {
    const source = makePublicSummary(parseLocalReport(JSON.stringify(completeInput())));
    const parsed: Record<string, unknown> = JSON.parse(JSON.stringify(source));
    const stages = parsed.stages as Record<string, Record<string, unknown>>;
    delete stages.schema.duration_ms;
    expect(() => parseLocalReport(JSON.stringify(parsed))).toThrow();
  });

  it('rejects duplicate JSON keys rather than accepting a different last value', () => {
    const source = JSON.stringify(completeInput());
    const duplicated = source.replace('"schema_version":"1.0"', '"schema_version":"unsupported","schema_version":"1.0"');
    expect(duplicated).not.toBe(source);
    expect(() => parseLocalReport(duplicated)).toThrow();
  });

  it('rejects escaped-equivalent duplicate keys and allows braces inside a string value', () => {
    const source = JSON.stringify(completeInput());
    const duplicated = source.replace('"schema_version":"1.0"', '"schema_version":"1.0","schema_versi\\u006fn":"1.0"');
    expect(() => parseLocalReport(duplicated)).toThrow();
    const control = completeInput();
    control.artifact.name = 'literal { "nested": "text" }';
    expect(parseLocalReport(JSON.stringify(control)).report.artifact.name).toBe(control.artifact.name);
  });

  it('rejects an oversized array before allocating its full parsed tree', () => {
    const source = JSON.stringify({ schema_version: '1.0', oversized: Array(2501).fill(null) });
    const parse = vi.spyOn(JSON, 'parse');
    try {
      expect(() => parseLocalReport(source)).toThrow();
      expect(parse.mock.calls.some(([value]) => value === source)).toBe(false);
    } finally { parse.mockRestore(); }
  });
});
