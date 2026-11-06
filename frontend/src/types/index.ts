import type { components } from '../api/generated';

// Omit must operate on named fields: OpenAPI permits additional properties on
// several DTOs, whose string index signature would otherwise erase these keys.
type DefinedFields<T> = { [Key in keyof T as string extends Key ? never : number extends Key ? never : Key]: T[Key] };
// Regenerate with npm run generate:api after exporting the backend OpenAPI.
export type ScanSummary = components['schemas']['ScanSummary'];
export type ScanStatus = ScanSummary['status'];
export type Finding = components['schemas']['Finding'];
export type Severity = Finding['severity'];
export type StageResult = components['schemas']['StageResult'];
export interface Page<T> { items: T[]; total: number }
export type UploadResult = components['schemas']['UploadResult'];
export type ScanCreated = components['schemas']['ScanCreated'] & { status: ScanStatus };
export interface QualityDimension {
  dimension: string; weight: number; status: string; score: number | null; metric?: string;
  numerator?: number | null; denominator?: number | null; checks?: unknown[]; reason?: string | null;
  runner_version?: string; evidence_ref?: unknown;
}
// The backend currently describes nested report dictionaries without schemas;
// only these dictionaries are refined locally, retaining generated top-level DTOs.
export type QualityReport = Omit<DefinedFields<components['schemas']['QualityReport']>, 'dimensions'> & { dimensions: QualityDimension[] };
export interface InventoryEntry { path: string; size: number; sha256: string; kind: string; hidden: boolean; executable: boolean; parseable: boolean }
export type FullReport = Omit<DefinedFields<components['schemas']['FullReport']>, 'artifact' | 'engines' | 'compliance' | 'security' | 'quality' | 'decision' | 'provenance' | 'logs'> & {
  artifact: { name: string; sha256: string; files: number; version_id: string; version_label: string | null; manifest: Record<string, unknown>; inventory: InventoryEntry[] };
  engines: Array<StageResult & { name: string; version: string }>;
  compliance: { status: string; issues: Array<{ code: string; file_path: string; line: number }> };
  security: { verdict: string; risk_index: number; findings: Finding[]; finding_counts: Record<string, number>; coverage: Record<string, boolean>; limitations: string[] };
  quality: QualityReport;
  decision: { status: string; reasons: string[]; required_stages: string[]; scope: string };
  provenance: { policy_version: string; ruleset_version: string; ruleset_sha256: string; scanner_source_sha256: string; policy_snapshot: Record<string, unknown>; limits: Record<string, number> };
  logs: Array<{ event: string; stage: string; status: string; duration_ms: number; reason: string | null }>;
}
export type ScanDiff = Omit<DefinedFields<components['schemas']['ScanDiff']>, 'changed_evidence' | 'quality_changes' | 'coverage_changes' | 'comparability'> & {
  changed_evidence: Array<{ left: Finding; right: Finding }>;
  quality_changes: Array<{ dimension: string; left_score: number | null; right_score: number | null; delta: number | null }>;
  coverage_changes: { left: Record<string, StageResult>; right: Record<string, StageResult> };
  comparability: { comparable: boolean; reasons: string[] };
}
