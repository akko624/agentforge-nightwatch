import type { Finding, FullReport, ScanSummary, Severity, StageResult } from '../types';

export const MAX_REPORT_BYTES = 5 * 1024 * 1024;
const levels: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const stageNames = ['schema', 'static', 'dependencies', 'semantic', 'dynamic', 'quality'] as const;
const stageStatuses = ['NOT_RUN', 'RUNNING', 'PASSED', 'FINDINGS', 'PARTIAL', 'ERROR', 'TIMEOUT', 'UNAVAILABLE'];
const dimensionWeights: Record<string, number> = { conformance: 0.2, maintainability: 0.2, correctness: 0.4, reliability: 0.2 };
const categories = new Set(['credential-exfiltration', 'remote-code-execution', 'dangerous-execution', 'unsupported-payload', 'prompt-injection', 'sensitive-filesystem', 'plaintext-secret', 'mutable-instructions', 'permission-conflict', 'path-traversal', 'dependency-coverage', 'install-hook', 'high-impact-action', 'overbroad-permissions', 'maintainability', 'conformance']);

export class ReportImportError extends Error {
  constructor(public code: string, message: string) { super(message); this.name = 'ReportImportError'; }
}
function invalid(): never { throw new ReportImportError('INVALID_REPORT', '报告格式或统计不一致，请选择 SQSP 导出的 JSON。'); }
function record(value: unknown): Record<string, unknown> { if (!value || typeof value !== 'object' || Array.isArray(value)) invalid(); return value as Record<string, unknown>; }
function array(value: unknown, limit: number): unknown[] { if (!Array.isArray(value) || value.length > limit) invalid(); return value; }
function num(value: unknown, max = 100, integer = false): number { if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > max || (integer && !Number.isInteger(value))) invalid(); return value; }
function optionalScore(value: unknown): number | null { return value === null ? null : num(value); }
function choice<T extends string>(value: unknown, choices: readonly T[]): T { if (typeof value !== 'string' || !choices.includes(value as T)) invalid(); return value as T; }
function text(value: unknown, limit = 500): string {
  if (typeof value !== 'string' || value.length > limit * 4) invalid();
  return value.replace(/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)/g, '[REDACTED]')
    .replace(/\b(?:sk-[\w-]{12,}|gh[pousr]_[\w]{16,}|github_pat_[\w]{16,}|AKIA[A-Z0-9]{16})\b/g, '[REDACTED]')
    .replace(/(?:api[_-]?key|(?:access[_-]?)?token|(?:client[_-]?)?secret|password|authorization)["']?\s*[:=]\s*["']?[^\s"',;}{]{6,}["']?/gi, '[REDACTED]')
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]{8,}/gi, '[REDACTED]').slice(0, limit);
}
function optionalText(value: unknown, limit = 500): string | null { return value === null || value === undefined ? null : text(value, limit); }

function boundedTree(value: unknown): void {
  const work: Array<[unknown, number]> = [[value, 0]]; let nodes = 0;
  while (work.length) {
    const [node, depth] = work.pop()!;
    if (++nodes > 80000 || depth > 20) invalid();
    if (typeof node === 'number' && !Number.isFinite(node)) invalid();
    if (node && typeof node === 'object') {
      if (Array.isArray(node) && node.length > 2500) invalid();
      const entries = Object.entries(node);
      if (entries.length > 2500) invalid();
      for (const [key, child] of entries) {
        if (['__proto__', 'prototype', 'constructor'].includes(key)) invalid();
        work.push([child, depth + 1]);
      }
    }
  }
}

function uniqueJsonKeys(source: string): void {
  // JSON.parse has no duplicate-key hook. This bounded lexical pass checks
  // object keys (including escaped spellings) before the native parser runs.
  const frames: Array<{ object: boolean; expectsKey: boolean; expectsValue: boolean; elements: number; keys: Set<string> }> = [];
  let nodes = 0;
  function beginValue() {
    if (++nodes > 80000) invalid();
    const frame = frames.at(-1);
    if (!frame) return;
    if (!frame.expectsValue) invalid();
    frame.expectsValue = false;
    if (!frame.object && ++frame.elements > 2500) invalid();
  }
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (char === '"') {
      const start = index; index += 1;
      while (index < source.length && source[index] !== '"') { if (source[index] === '\\') index += 1; index += 1; }
      if (index >= source.length) invalid();
      const frame = frames.at(-1);
      if (frame?.object && frame.expectsKey) {
        const key = JSON.parse(source.slice(start, index + 1)) as string;
        if (frame.keys.has(key) || frame.keys.size >= 2500) invalid();
        frame.keys.add(key); frame.expectsKey = false; frame.expectsValue = true;
      } else beginValue();
    } else if (char === '{' || char === '[') {
      beginValue();
      if (frames.length >= 20) invalid();
      frames.push({ object: char === '{', expectsKey: char === '{', expectsValue: char === '[', elements: 0, keys: new Set() });
    } else if (char === '}' || char === ']') {
      if (!frames.length) invalid();
      frames.pop();
    } else if (char === ',') {
      const frame = frames.at(-1);
      if (!frame) invalid();
      frame.expectsKey = frame.object; frame.expectsValue = !frame.object;
    } else if (char !== ':' && !/\s/.test(char)) {
      beginValue();
      while (index + 1 < source.length && !/[\s,}\]]/.test(source[index + 1])) index += 1;
    }
  }
}

function counts(value: unknown): Record<string, number> {
  const data = record(value); const result: Record<string, number> = {};
  for (const level of levels) result[level.toLowerCase()] = num(data[level.toLowerCase()] ?? 0, 2000, true);
  if (Object.values(result).reduce((a, b) => a + b, 0) > 2000) invalid();
  return result;
}
function stages(value: unknown, publicMode = false): Record<string, StageResult> {
  const data = record(value); const result: Record<string, StageResult> = {};
  for (const name of stageNames) {
    if (!(name in data)) continue;
    const row = record(data[name]);
    result[name] = { status: choice(row.status, stageStatuses), reason: publicMode ? null : optionalText(row.reason), duration_ms: num(row.duration_ms, 86_400_000, true), coverage: {} };
  }
  if (!result.schema || !result.static || !result.quality) invalid();
  return result;
}

function quality(value: unknown): FullReport['quality'] {
  const data = record(value);
  const dimensions = array(data.dimensions, 4).map((entry) => {
    const item = record(entry); const dimension = choice(item.dimension, Object.keys(dimensionWeights));
    if (num(item.weight, 1) !== dimensionWeights[dimension]) invalid();
    const score = optionalScore(item.score); const status = choice(item.status, stageStatuses);
    if (!['PASSED', 'FINDINGS'].includes(status) && score !== null) invalid();
    return { dimension, weight: dimensionWeights[dimension], status, score, metric: 'imported_report_value', reason: optionalText(item.reason) };
  });
  if (new Set(dimensions.map((d) => d.dimension)).size !== 4) invalid();
  const observed = dimensions.filter((d) => ['PASSED', 'FINDINGS'].includes(d.status) && d.score !== null).reduce((sum, d) => sum + d.weight, 0);
  const coverage = num(data.coverage, 1);
  if (Math.abs(observed - coverage) > 0.0001) invalid();
  const score = optionalScore(data.score);
  if (score !== null && coverage < 0.9999) invalid();
  const staticScore = optionalScore(data.static_subscore);
  const staticDimensions = dimensions.filter((d) => ['conformance', 'maintainability'].includes(d.dimension));
  if (staticScore !== null && (staticDimensions.some((d) => d.score === null) || Math.abs(staticScore - staticDimensions.reduce((sum, d) => sum + (d.score ?? 0), 0) / 2) > 0.011)) invalid();
  if (score !== null && Math.abs(score - dimensions.reduce((sum, d) => sum + (d.score ?? 0) * d.weight, 0)) > 0.011) invalid();
  return { score, coverage, static_subscore: staticScore, dimensions, reasons: ['文件由用户提供，数值及执行来源未经过服务端或数字签名验证。'] };
}

export interface PublicSummary {
  schema_version: 'sqsp-public-1.0';
  scope: 'AGGREGATE_ONLY';
  status: 'PARTIAL' | 'COMPLETED';
  file_count: number;
  severity_counts: Record<string, number>;
  category_counts: Record<string, number>;
  rule_counts: Record<string, number>;
  stages: Record<string, StageResult>;
  quality: FullReport['quality'];
  security_verdict: string;
  security_risk_index: number;
  release_decision: string;
}
export interface LocalDocument {
  report: FullReport; scan: ScanSummary; mode: 'full' | 'aggregate';
  aggregates?: { categoryCounts: Record<string, number>; ruleCounts: Record<string, number> };
}

function summaryScan(report: FullReport, stageData: Record<string, StageResult>): ScanSummary {
  return { scan_id: '', skill_id: '', version_id: '', skill_name: report.artifact.name, version_label: report.artifact.version_label,
    artifact_sha256: report.artifact.sha256, status: report.scan.status as ScanSummary['status'], stages: stageData,
    quality_score: report.quality.score, quality_coverage: report.quality.coverage, static_quality_subscore: report.quality.static_subscore,
    security_risk_index: report.security.risk_index, security_verdict: report.security.verdict, release_decision: report.decision.status,
    finding_counts: report.security.finding_counts, policy_version: report.provenance.policy_version, scanner_versions: {},
    created_at: '', started_at: null, completed_at: null, error_code: null, attempts: 0 };
}

function readFull(data: Record<string, unknown>): LocalDocument {
  const scan = record(data.scan), artifact = record(data.artifact), security = record(data.security), decision = record(data.decision);
  const provenance = record(data.provenance), compliance = record(data.compliance);
  const findings: Finding[] = array(security.findings, 2000).map((entry, index) => {
    const f = record(entry); const start = num(f.line_start, 10_000_000, true), end = num(f.line_end, 10_000_000, true);
    if (start < 1 || end < start) invalid();
    return { rule_id: text(f.rule_id, 80), category: text(f.category, 80), engine: text(f.engine, 80), severity: choice(f.severity, levels),
      confidence: choice(f.confidence, ['LOW', 'MEDIUM', 'HIGH'] as const), file_path: text(f.file_path, 512), line_start: start, line_end: end,
      evidence_excerpt: text(f.evidence_excerpt ?? '', 4000), message: text(f.message, 1000), remediation: text(f.remediation ?? '', 1000),
      context_note: optionalText(f.context_note), fingerprint: `imported-${index}`, status: text(f.status ?? 'OPEN', 30),
      matched_rule_version: text(f.matched_rule_version, 50), engine_version: text(f.engine_version, 50) };
  });
  const findingCounts = counts(security.finding_counts);
  for (const level of levels) if (findings.filter((f) => f.severity === level).length !== findingCounts[level.toLowerCase()]) invalid();
  const inventory = array(artifact.inventory, 300).map((entry) => {
    const f = record(entry);
    if (typeof f.hidden !== 'boolean' || typeof f.executable !== 'boolean' || typeof f.parseable !== 'boolean') invalid();
    return { path: text(f.path, 512), size: num(f.size, 10 * 1024 * 1024, true), sha256: text(f.sha256, 64), kind: text(f.kind, 30), hidden: f.hidden, executable: f.executable, parseable: f.parseable };
  });
  if (num(artifact.files, 300, true) !== inventory.length) invalid();
  const stageData: Record<string, StageResult> = {};
  for (const entry of array(data.engines, 20)) {
    const engine = record(entry); const name = choice(engine.name, stageNames);
    if (stageData[name]) invalid();
    stageData[name] = { status: choice(engine.status, stageStatuses), reason: optionalText(engine.reason), duration_ms: num(engine.duration_ms, 86_400_000, true), coverage: {} };
  }
  const checkedStages = stages(stageData);
  const report: FullReport = {
    schema_version: '1.0', scan: { status: choice(scan.status, ['PARTIAL', 'COMPLETED']) },
    artifact: { name: text(artifact.name, 64), sha256: text(artifact.sha256, 64), files: inventory.length, version_id: '', version_label: optionalText(artifact.version_label, 64), manifest: {}, inventory },
    security: { verdict: choice(security.verdict, ['PASS', 'REVIEW', 'BLOCK', 'UNKNOWN']), risk_index: num(security.risk_index), findings, finding_counts: findingCounts,
      coverage: {}, limitations: ['导入的报告未验签，不能作为平台认证或完整安全保证。'] },
    quality: quality(data.quality), compliance: { status: choice(compliance.status, stageStatuses), issues: [] },
    engines: Object.entries(checkedStages).map(([name, result]) => ({ name, version: '', ...result })),
    decision: { status: choice(decision.status, ['ALLOW', 'REVIEW', 'BLOCK', 'INCOMPLETE']), reasons: [], required_stages: [], scope: '导入文件中的原始门禁结论，执行来源未验证' },
    provenance: { policy_version: text(provenance.policy_version, 50), ruleset_version: text(provenance.ruleset_version, 50), ruleset_sha256: '', scanner_source_sha256: '', policy_snapshot: {}, limits: {} },
    permissions: {}, logs: [],
  };
  return { report, scan: summaryScan(report, checkedStages), mode: 'full' };
}

function aggregateCounts(value: unknown, allowed: (key: string) => boolean): Record<string, number> {
  const data = record(value); if (Object.keys(data).length > 40) invalid();
  const result: Record<string, number> = {};
  for (const [key, count] of Object.entries(data)) { if (!allowed(key)) invalid(); result[key] = num(count, 2000, true); }
  return result;
}
function readPublic(data: Record<string, unknown>): LocalDocument {
  if (data.scope !== 'AGGREGATE_ONLY') invalid();
  const stageData = stages(data.stages, true), q = quality(data.quality);
  const totals = counts(data.severity_counts);
  const categoryCounts = aggregateCounts(data.category_counts, (key) => categories.has(key) || key === 'other');
  const ruleCounts = aggregateCounts(data.rule_counts, (key) => /^SQSP-(S00[1-9]|S01[0-6]|C001)$/.test(key) || key === 'OTHER');
  const total = Object.values(totals).reduce((a, b) => a + b, 0);
  if (Object.values(categoryCounts).reduce((a, b) => a + b, 0) !== total || Object.values(ruleCounts).reduce((a, b) => a + b, 0) !== total) invalid();
  const report: FullReport = { schema_version: '1.0', scan: { status: choice(data.status, ['PARTIAL', 'COMPLETED']) },
    artifact: { name: 'Skill 验证报告', sha256: '', files: num(data.file_count, 300, true), version_id: '', version_label: null, inventory: [], manifest: {} },
    security: { verdict: choice(data.security_verdict, ['PASS', 'REVIEW', 'BLOCK', 'UNKNOWN']), risk_index: num(data.security_risk_index), findings: [], finding_counts: totals, coverage: {}, limitations: ['公开摘要不含文件位置和原文证据，不能用来复核全部发现。'] },
    quality: { ...q, dimensions: q.dimensions.map((d) => ({ ...d, reason: undefined })) }, compliance: { status: stageData.schema.status, issues: [] },
    engines: Object.entries(stageData).map(([name, result]) => ({ name, version: '', ...result })),
    decision: { status: choice(data.release_decision, ['ALLOW', 'REVIEW', 'BLOCK', 'INCOMPLETE']), reasons: [], required_stages: [], scope: '用户提供的未验签聚合摘要' },
    provenance: { policy_version: '', ruleset_version: '', ruleset_sha256: '', scanner_source_sha256: '', policy_snapshot: {}, limits: {} }, permissions: {}, logs: [] };
  return { report, scan: summaryScan(report, stageData), mode: 'aggregate', aggregates: { categoryCounts, ruleCounts } };
}

export function parseLocalReport(source: string): LocalDocument {
  if (new TextEncoder().encode(source).length > MAX_REPORT_BYTES) throw new ReportImportError('REPORT_TOO_LARGE', '报告超过 5 MiB 限制。');
  let value: unknown;
  try { uniqueJsonKeys(source); value = JSON.parse(source); } catch { invalid(); }
  boundedTree(value);
  const data = record(value);
  if (data.schema_version === '1.0') return readFull(data);
  if (data.schema_version === 'sqsp-public-1.0') return readPublic(data);
  throw new ReportImportError('UNSUPPORTED_REPORT', '不支持的报告版本；请选择 SQSP 完整报告或聚合摘要。');
}

export function makePublicSummary(document: LocalDocument): PublicSummary {
  const { report, scan } = document;
  const categoryCounts: Record<string, number> = {}, ruleCounts: Record<string, number> = {};
  for (const finding of report.security.findings) {
    const category = categories.has(finding.category) ? finding.category : 'other';
    const rule = /^SQSP-(S00[1-9]|S01[0-6]|C001)$/.test(finding.rule_id) ? finding.rule_id : 'OTHER';
    categoryCounts[category] = (categoryCounts[category] ?? 0) + 1; ruleCounts[rule] = (ruleCounts[rule] ?? 0) + 1;
  }
  return { schema_version: 'sqsp-public-1.0', scope: 'AGGREGATE_ONLY', status: scan.status as 'PARTIAL' | 'COMPLETED',
    file_count: report.artifact.files, severity_counts: counts(report.security.finding_counts),
    category_counts: document.aggregates?.categoryCounts ?? categoryCounts, rule_counts: document.aggregates?.ruleCounts ?? ruleCounts,
    stages: Object.fromEntries(Object.entries(scan.stages).map(([name, value]) => [name, { status: value.status, reason: null, duration_ms: value.duration_ms, coverage: {} }])),
    quality: { score: report.quality.score, coverage: report.quality.coverage, static_subscore: report.quality.static_subscore,
      dimensions: report.quality.dimensions.map((d) => ({ dimension: d.dimension, weight: d.weight, status: d.status, score: d.score })), reasons: [] },
    security_verdict: report.security.verdict, security_risk_index: report.security.risk_index, release_decision: report.decision.status };
}
