import { lazy, Suspense } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Result, Space, Spin, Tag } from 'antd';
import { SafetyCertificateOutlined, UploadOutlined } from '@ant-design/icons';
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { request } from './api/client';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const UploadPage = lazy(() => import('./pages/UploadPage'));
const ReportPage = lazy(() => import('./pages/ReportPage'));
const ComparePage = lazy(() => import('./pages/ComparePage'));
const ReportViewer = lazy(() => import('./pages/ReportViewer'));

export function AppRoutes() {
  const localViewer = useLocation().pathname === '/viewer';
  const health = useQuery({ queryKey: ['health'], queryFn: () => request<unknown>('/healthz'), refetchInterval: localViewer ? false : 30_000, enabled: !localViewer });
  return <div className="app-shell">
    <header className="topbar">
      <Link to="/" className="brand"><SafetyCertificateOutlined className="brand-icon" /><strong>AgentForge</strong><span className="brand-description">NightWatch · Agent 工件安全与进化平台</span></Link>
      <nav aria-label="主导航"><NavLink to="/" end>扫描工作台</NavLink><NavLink to="/compare">版本对比</NavLink><NavLink to="/viewer">本地报告查看</NavLink></nav>
      <Space>{localViewer ? <Tag>浏览器本地查看</Tag> : <Tag color={health.isSuccess ? 'green' : health.isError ? 'red' : 'default'}>{health.isSuccess ? 'API 在线' : health.isError ? 'API 未连接' : '连接中'}</Tag>}<Link to="/upload"><Button type="primary" icon={<UploadOutlined />}>上传 Skill</Button></Link></Space>
    </header>
    <main>
      {!localViewer && health.isError && <Alert type="error" showIcon className="section-gap" message="API 未连接" description="请确认后端服务已启动。已有页面状态可能尚未刷新。" />}
      <Suspense fallback={<div className="loading-panel"><Spin size="large" tip="正在加载页面"><div style={{ height: 80 }} /></Spin></div>}>
        <Routes>
          <Route path="/" element={<Dashboard />} /><Route path="/upload" element={<UploadPage />} />
          <Route path="/scans/:id" element={<ReportPage />} /><Route path="/compare" element={<ComparePage />} />
          <Route path="/viewer" element={<ReportViewer />} />
          <Route path="*" element={<Result status="404" title="页面不存在" extra={<Link to="/">返回工作台</Link>} />} />
        </Routes>
      </Suspense>
      <footer className="footer">AgentForge NightWatch · 当前以 Skill 为首个工件类型 · 静态检测不会执行上传代码 · 未运行项不会视为通过</footer>
    </main>
  </div>;
}
export function App() { return <BrowserRouter><AppRoutes /></BrowserRouter>; }
