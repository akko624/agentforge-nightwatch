import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import ReportViewer from './pages/ReportViewer';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#176b50', borderRadius: 8, fontFamily: 'Inter, "Segoe UI", "Microsoft YaHei", sans-serif' } }}><div className="app-shell"><header className="topbar"><span className="brand"><strong>AgentForge</strong><span className="brand-description">NightWatch · 公开报告与本地查看器</span></span><span className="viewer-static-badge">无扫描后端连接</span></header><main><ReportViewer /><footer className="footer">报告来自导入文件或发布者提供的摘要 · 未经平台验签 · 未执行上传的 Skill</footer></main></div></ConfigProvider></React.StrictMode>);
