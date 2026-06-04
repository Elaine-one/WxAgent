import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import LLMConfig from './pages/LLMConfig'
import Security from './pages/Security'
import Limits from './pages/Limits'
import Workspace from './pages/Workspace'
import Memory from './pages/Memory'
import Tools from './pages/Tools'
import Prompts from './pages/Prompts'
import Scenarios from './pages/Scenarios'
import SystemControl from './pages/SystemControl'
import ToolRegistry from './pages/ToolRegistry'
import McpManage from './pages/McpManage'
import FeishuManage from './pages/FeishuManage'

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
        },
        algorithm: theme.defaultAlgorithm,
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="llm" element={<LLMConfig />} />
            <Route path="security" element={<Security />} />
            <Route path="limits" element={<Limits />} />
            <Route path="workspace" element={<Workspace />} />
            <Route path="memory" element={<Memory />} />
            <Route path="tools" element={<Tools />} />
            <Route path="tool-registry" element={<ToolRegistry />} />
            <Route path="prompts" element={<Prompts />} />
            <Route path="scenarios" element={<Scenarios />} />
            <Route path="system" element={<SystemControl />} />
            <Route path="mcp" element={<McpManage />} />
            <Route path="feishu" element={<FeishuManage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App
