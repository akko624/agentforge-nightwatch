import { useId } from 'react';
import { CheckCircleOutlined, FileSearchOutlined, SafetyCertificateOutlined, WarningOutlined } from '@ant-design/icons';
import type { FullReport, ScanSummary, Severity } from '../../types';
import './report.css';

const levels: Array<{ severity: Severity; label: string; color: string }> = [
  { severity: 'CRITICAL', label: '严重', color: '#a92d3b' },
  { severity: 'HIGH', label: '高风险', color: '#d86632' },
  { severity: 'MEDIUM', label: '中风险', color: '#b58620' },
  { severity: 'LOW', label: '低风险', color: '#35759c' },
  { severity: 'INFO', label: '提示', color: '#7f8d88' },
];
const stageNames: Record<string, string> = { schema: '规范校验', static: '静态安全', dependencies: '依赖漏洞', semantic: '语义检测', dynamic: '动态沙箱', quality: '质量评测' };
const stateNames: Record<string, string> = { PASSED: '已完成', FINDINGS: '发现问题', PARTIAL: '部分完成', NOT_RUN: '未运行', UNAVAILABLE: '不可用', RUNNING: '运行中', ERROR: '错误', TIMEOUT: '超时' };
const dimensionNames: Record<string, string> = { conformance: '规范符合性', maintainability: '可理解性与维护性', correctness: '功能正确性', reliability: '稳定性与效率' };
const securityNames: Record<string, string> = { BLOCK: '阻断', REVIEW: '需复核', PASS: '当前检查通过', UNKNOWN: '未知' };
const decisions: Record<string, { title: string; detail: string; tone: string }> = {
  BLOCK: { title: '阻断发布', detail: '存在阻断证据。先审查风险链与整改建议，再重新扫描。', tone: 'block' },
  INCOMPLETE: { title: '证据不足', detail: '必需阶段尚未完整评测，当前结果不足以批准发布。', tone: 'incomplete' },
  REVIEW: { title: '需要人工审查', detail: '存在需要复核的风险候选，请结合证据和实际用途判断。', tone: 'review' },
  ALLOW: { title: '当前门禁允许', detail: '符合当前明确配置的检查要求；结论只适用于已测范围。', tone: 'allow' },
};
const readableBytes = (bytes: number) => bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MiB` : bytes >= 1024 ? `${(bytes / 1024).toFixed(1)} KiB` : `${bytes} B`;
const completed = (state: string) => ['PASSED', 'FINDINGS'].includes(state);

export interface ReportBoardProps {
  report: FullReport;
  scan: ScanSummary;
  onSeveritySelect?: (severity: Severity) => void;
  selectedSeverity?: Severity;
  detailVisibility?: 'full' | 'aggregate';
  aggregates?: { categoryCounts?: Record<string, number>; ruleCounts?: Record<string, number> };
  provenanceMode?: 'platform' | 'imported';
}

export function ReportBoard({ report, scan, onSeveritySelect, selectedSeverity, detailVisibility = 'full', aggregates, provenanceMode = 'platform' }: ReportBoardProps) {
  const chartId = useId();
  const findings = report.security.findings;
  const distribution = levels.map((level) => ({ ...level, count: report.security.finding_counts[level.severity.toLowerCase()] ?? findings.filter((finding) => finding.severity === level.severity).length }));
  const total = distribution.reduce((sum, level) => sum + level.count, 0);
  const aggregateOnly = detailVisibility === 'aggregate' || total > 0 && findings.length === 0;
  const uniqueRules = aggregateOnly ? aggregates?.ruleCounts ? Object.keys(aggregates.ruleCounts).length : null : new Set(findings.map((finding) => finding.rule_id)).size;
  const critical = distribution[0].count;
  const high = distribution[1].count;
  const fileMap = new Map<string, { path: string; total: number; high: number; categories: Set<string> }>();
  for (const finding of findings) {
    const item = fileMap.get(finding.file_path) ?? { path: finding.file_path, total: 0, high: 0, categories: new Set<string>() };
    item.total += 1;
    item.high += ['CRITICAL', 'HIGH'].includes(finding.severity) ? 1 : 0;
    item.categories.add(finding.category);
    fileMap.set(finding.file_path, item);
  }
  const topFiles = [...fileMap.values()].sort((a, b) => b.high - a.high || b.total - a.total || a.path.localeCompare(b.path)).slice(0, 5);
  const stages = Object.entries(scan.stages);
  const finishedStages = stages.filter(([, stage]) => completed(stage.status)).length;
  const timedStages = stages.filter(([, stage]) => !['NOT_RUN', 'UNAVAILABLE'].includes(stage.status) && typeof stage.duration_ms === 'number' && Number.isFinite(stage.duration_ms));
  const maxDuration = Math.max(0, ...timedStages.map(([, stage]) => stage.duration_ms!));
  const measuredDuration = timedStages.reduce((sum, [, stage]) => sum + stage.duration_ms!, 0);
  const coverage = Math.max(0, Math.min(1, report.quality.coverage));
  const coverPercent = Math.round(coverage * 100);
  const circumference = 2 * Math.PI * 54;
  const decision = decisions[scan.release_decision] ?? { title: '结论待确认', detail: '请检查报告阶段与门禁记录，不能将未知状态视为通过。', tone: 'incomplete' };
  const score = report.quality.static_subscore;
  const riskIndex = scan.security_risk_index;
  const normalizedRiskIndex = typeof riskIndex === 'number' && Number.isFinite(riskIndex) ? Math.max(0, Math.min(100, riskIndex)) : null;
  const totalBytes = report.artifact.inventory.reduce((sum, file) => sum + file.size, 0);
  const categoryRows = Object.entries(aggregates?.categoryCounts ?? {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 5);
  const ruleVersion = report.provenance.ruleset_version.trim() || '未披露';
  const policyVersion = report.provenance.policy_version.trim() || '未披露';

  return <section className="sqsp-report-board" aria-label="验证报告核心看板">
    <div className="report-board-title"><span className="report-board-kicker">EVIDENCE OVERVIEW</span><span>{provenanceMode === 'imported' ? '用户提供的报告 · 执行来源未验签' : '基于本次真实扫描'} · 规则集 {ruleVersion}</span></div>
    <div className="board-command-deck">
      <div className="board-command-copy">
        <span className="board-command-eyebrow"><span className="board-live-dot" /> DECISION CONSOLE / {scan.status}</span>
        <h2>先看证据密度<br />再决定是否发布</h2>
        <p>这不是安全认证面板。它将本次扫描的风险、覆盖与执行状态放在同一视野，方便团队快速进入需要人工判断的证据。</p>
        <div className="board-command-badges"><span>{finishedStages} / {stages.length || 0} 阶段完整完成</span><span>{coverPercent}% 质量权重已测</span><span>{aggregateOnly ? '已隐藏证据细节' : '未执行上传代码'}</span></div>
      </div>
      <div className="board-command-signal" aria-label={normalizedRiskIndex === null ? '风险指数未记录' : `风险指数 ${normalizedRiskIndex} / 100，仅用于审阅排序`}>
        <div className="board-signal-orbit board-signal-orbit-a" /><div className="board-signal-orbit board-signal-orbit-b" />
        <div className="board-signal-core"><span>RISK PULSE</span><strong>{normalizedRiskIndex ?? '—'}</strong><small>/ 100</small><em>{securityNames[scan.security_verdict] ?? scan.security_verdict}</em></div>
        <svg className="board-signal-meter" viewBox="0 0 200 200" role="img" aria-label={normalizedRiskIndex === null ? '风险指数未记录' : `风险指数 ${normalizedRiskIndex} / 100，仅用于审阅排序`}>
          <circle cx="100" cy="100" r="82" fill="none" stroke="rgba(255,255,255,.11)" strokeWidth="4" />
          {normalizedRiskIndex !== null && <circle className="board-signal-meter-value" cx="100" cy="100" r="82" fill="none" stroke={`url(#${chartId}-risk-meter-gradient)`} strokeWidth="4" strokeLinecap="round" strokeDasharray={`${normalizedRiskIndex / 100 * 515.22} 515.22`} transform="rotate(-90 100 100)" />}
          <defs><linearGradient id={`${chartId}-risk-meter-gradient`} x1="0" x2="1"><stop stopColor="#f2d985" /><stop offset=".52" stopColor="#f08361" /><stop offset="1" stopColor="#e85e6c" /></linearGradient></defs>
        </svg>
        <span className="board-signal-caption">仅用于审阅排序</span>
      </div>
      <div className="board-command-lanes" aria-label="各严重等级的发现数量">
        {distribution.map((level) => <div className="board-command-lane" key={level.severity}><div><span style={{ background: level.color }} /><code>{level.severity}</code><strong>{level.count}</strong></div><i style={{ width: `${total ? Math.max(8, level.count / total * 100) : 8}%`, background: level.color }} /></div>)}
      </div>
    </div>
    <div className="report-board-summary">
      <article className={`board-decision board-decision-${decision.tone}`}>
        <div className="board-decision-top"><span><SafetyCertificateOutlined /> {provenanceMode === 'imported' ? '报告声明的发布决策' : '发布决策'}</span><code>{scan.release_decision}</code></div>
        <h2>{decision.title}</h2><p>{decision.detail}</p>
        <div className="board-decision-foot"><span>策略 {policyVersion}</span><span>不等于全面安全认证</span></div>
      </article>
        <div className="board-kpi"><span className="board-kpi-icon board-icon-risk"><WarningOutlined /></span><span className="board-kpi-label">风险发现</span><strong>{total}<small> 条</small></strong><span className="board-kpi-note">严重 {critical} · 高风险 {high}{uniqueRules !== null && ` · ${uniqueRules} 条规则`}</span><span className="board-kpi-note">安全结论：{securityNames[scan.security_verdict] ?? scan.security_verdict} · {scan.security_verdict}</span><span className="board-kpi-note">风险指数 {normalizedRiskIndex ?? '—'} / 100，仅用于审阅排序</span></div>
      <div className="board-kpi"><span className="board-kpi-icon"><CheckCircleOutlined /></span><span className="board-kpi-label">局部静态质量</span><strong>{score === null ? '未评测' : score.toFixed(1)}{score !== null && <small> / 100</small>}</strong><span className="board-kpi-note">完整质量分：{report.quality.score === null ? '未评测（null）' : report.quality.score}</span><span className="board-kpi-note">结构与说明的启发式，不代表任务成功率</span></div>
      <div className="board-kpi"><span className="board-kpi-icon board-icon-file"><FileSearchOutlined /></span><span className="board-kpi-label">已编目文件</span><strong>{report.artifact.files}<small> 个</small></strong><span className="board-kpi-note">{aggregateOnly ? '公开摘要未包含完整文件清单' : `${readableBytes(totalBytes)} · ${report.artifact.inventory.filter((file) => file.hidden).length} 个隐藏文件`}</span><span className="board-kpi-note">{aggregateOnly ? '仅展示聚合检测结果' : provenanceMode === 'imported' ? '文件记录来自导入报告' : '逐文件 SHA256 · 上传代码未执行'}</span></div>
    </div>

    <div className="report-board-charts">
      <article className="board-panel board-risk-panel">
        <div className="board-panel-heading"><div><span className="board-panel-index">01 / RISK PROFILE</span><h3>风险分布与审查优先级</h3></div><span className="board-panel-meta">{total} 条发现</span></div>
        <div className="board-risk-total"><strong>{critical + high}</strong><span>条严重 / 高风险候选<br /><small>优先人工审查，不按命中直接推断恶意</small></span></div>
        <svg className="board-risk-bar" viewBox="0 0 600 26" role="img" aria-labelledby={`${chartId}-risk-title`}>
          <title id={`${chartId}-risk-title`}>{total ? distribution.map((level) => `${level.label}${level.count}条`).join('，') : '当前静态扫描未发现风险候选，不代表不存在风险'}</title>
          <rect x="0" y="0" width="600" height="26" rx="7" fill="#edf0ed" />
          {distribution.map((level, index) => {
            const x = distribution.slice(0, index).reduce((sum, item) => sum + item.count, 0) / Math.max(total, 1) * 600;
            return level.count > 0 && <rect key={level.severity} x={x} y="0" width={level.count / Math.max(total, 1) * 600} height="26" fill={level.color} />;
          })}
        </svg>
        <div className="board-risk-legend">{distribution.map((level) => <button key={level.severity} type="button" className={`board-legend-button${selectedSeverity === level.severity ? ' board-legend-selected' : ''}`} aria-pressed={selectedSeverity === level.severity} disabled={!onSeveritySelect} onClick={() => onSeveritySelect?.(level.severity)} aria-label={`按 ${level.severity} 筛选（${level.count} 条）`}>
          <span className="board-color-dot" style={{ background: level.color }} /><span>{level.label}<small>{level.severity}</small></span><strong>{level.count}</strong>
        </button>)}</div>
        <p className="board-panel-note">{onSeveritySelect ? '点击图例，定位下方同等级证据。' : '分布来自完整报告中的风险发现。'} {total === 0 ? '没有发现只表示本次规则未命中，不是安全证明。' : '等级是审查优先级，需结合置信度和上下文。'}</p>
      </article>

      <article className="board-panel board-coverage-panel">
        <div className="board-panel-heading"><div><span className="board-panel-index">02 / MEASUREMENT</span><h3>质量覆盖，保留未知</h3></div><span className="board-panel-meta">完整模型权重</span></div>
        <div className="board-coverage-content">
          <div className="board-ring-container"><svg className="board-coverage-ring" viewBox="0 0 140 140" role="img" aria-label={`质量评测覆盖 ${coverPercent}%，其余 ${100 - coverPercent}% 未完成`}>
            <circle cx="70" cy="70" r="54" fill="none" stroke="#edf0ed" strokeWidth="12" />
            <circle cx="70" cy="70" r="54" fill="none" stroke="#27694f" strokeWidth="12" strokeDasharray={`${coverage * circumference} ${circumference}`} transform="rotate(-90 70 70)" />
            <text x="70" y="68" textAnchor="middle" className="board-ring-value">{coverPercent}%</text><text x="70" y="89" textAnchor="middle" className="board-ring-label">已测权重</text>
          </svg><span>其余 {100 - coverPercent}% 未完成</span></div>
          <div className="board-dimensions">{report.quality.dimensions.map((dimension) => {
            const measured = dimension.score !== null && completed(dimension.status);
            return <div className="board-dimension" key={dimension.dimension}><div><span>{dimensionNames[dimension.dimension] ?? dimension.dimension}</span><strong>{Math.round(dimension.weight * 100)}%</strong></div><div className="board-weight-track"><span className={measured ? 'board-weight-measured' : 'board-weight-unknown'} style={{ width: `${Math.max(0, Math.min(1, dimension.weight)) * 100}%` }} /></div><small>{measured ? `本维度 ${dimension.score!.toFixed(1)} / 100` : `${stateNames[dimension.status] ?? dimension.status} · 不赋予分数`}</small></div>;
          })}</div>
        </div>
        <p className="board-panel-note">覆盖率是已完成维度权重之和，不是质量分或安全通过率。未测维度不补零、不按已测部分重算完整分。</p>
      </article>

      <article className="board-panel board-stage-panel">
        <div className="board-panel-heading"><div><span className="board-panel-index">03 / EXECUTION</span><h3>检测能力与执行轨迹</h3></div><span className="board-panel-meta">{stages.length ? `${finishedStages} / ${stages.length} 阶段完整完成` : '未提供阶段记录'}</span></div>
        <div className="board-stage-matrix">{stages.map(([name, stage]) => <div key={name} className={`board-stage board-state-${stage.status.toLowerCase()}`}><span className="board-stage-dot" /><strong>{stageNames[name] ?? name}</strong><span>{stateNames[stage.status] ?? stage.status}</span></div>)}</div>
        <div className="board-duration-header"><span>阶段记录耗时</span><strong>{timedStages.length ? `合计 ${measuredDuration} ms` : '未记录'}</strong></div>
        <div className="board-duration-chart" role="img" aria-label="各分析阶段记录耗时；未运行项无测量值">{stages.map(([name, stage]) => {
          const unavailable = ['NOT_RUN', 'UNAVAILABLE'].includes(stage.status);
          const hasMeasurement = !unavailable && typeof stage.duration_ms === 'number' && Number.isFinite(stage.duration_ms);
          return <div className="board-duration-row" key={name}><span>{stageNames[name] ?? name}</span><div className="board-duration-track">{hasMeasurement && <span style={{ width: `${maxDuration ? stage.duration_ms! / maxDuration * 100 : 0}%` }} />}</div><strong>{unavailable ? '未测' : hasMeasurement ? `${stage.duration_ms} ms` : '未记录'}</strong></div>;
        })}</div><p className="board-panel-note">合计为已记录的阶段处理耗时，不包含排队，也不是宿主任务延迟。部分完成与不可用能力不计为通过。</p>
      </article>

      <article className="board-panel board-files-panel">
        <div className="board-panel-heading"><div><span className="board-panel-index">04 / TRIAGE</span><h3>{aggregateOnly ? '风险分类概览' : '优先审查的文件'}</h3></div><span className="board-panel-meta">{aggregateOnly ? '公开摘要 · Top 5 分类' : '按高风险数排序 · Top 5'}</span></div>
        {aggregateOnly ? <><div className="board-table-wrap"><table className="board-triage-table"><caption className="board-sr-only">公开摘要的风险分类与对应发现数量</caption><thead><tr><th scope="col">风险分类</th><th scope="col">发现数</th></tr></thead><tbody>{categoryRows.length ? categoryRows.map(([category, count]) => <tr key={category}><th scope="row"><code>{category}</code><span className="board-file-track"><span style={{ width: `${count / Math.max(total, 1) * 100}%` }} /></span></th><td>{count}</td></tr>) : <tr><td colSpan={2} className="board-no-findings">公开摘要未包含分类明细。</td></tr>}</tbody></table></div><p className="board-panel-note">公开摘要未包含文件位置与证据；这些信息的缺失不表示文件中没有风险。</p></> : <><div className="board-table-wrap"><table className="board-triage-table"><caption className="board-sr-only">各文件的发现数量、严重及高风险数量与风险分类数</caption><thead><tr><th scope="col">文件 / 发现密度</th><th scope="col">高风险</th><th scope="col">全部</th><th scope="col">分类</th></tr></thead><tbody>
          {topFiles.length ? topFiles.map((file) => <tr key={file.path}><th scope="row"><code>{file.path}</code><span className="board-file-track"><span style={{ width: `${file.total / Math.max(total, 1) * 100}%` }} /></span></th><td><span className={file.high ? 'board-high-count' : ''}>{file.high}</span></td><td>{file.total}</td><td>{file.categories.size}</td></tr>) : <tr><td colSpan={4} className="board-no-findings">本次静态规则未命中文件风险；请继续查看检测覆盖。</td></tr>}
        </tbody></table></div><div className="board-files-foot"><span>{fileMap.size} / {report.artifact.inventory.length} 个编目文件关联发现</span><span>严重 + 高风险合并计数</span></div>
        <p className="board-panel-note">表格只表示风险证据集中位置。未命中的文件可能存在规则盲区，完整清单和 hash 可在下方查看。</p></>}
      </article>
    </div>
  </section>;
}
