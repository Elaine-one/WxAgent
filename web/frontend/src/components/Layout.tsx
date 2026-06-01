import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout as AntLayout, Menu, theme } from 'antd'
import {
  DashboardOutlined,
  RobotOutlined,
  SafetyOutlined,
  StopOutlined,
  FolderOutlined,
  SearchOutlined,
  ToolOutlined,
  FormOutlined,
  AppstoreOutlined,
  ControlOutlined,
  ApiOutlined,
} from '@ant-design/icons'
import { useServiceStore } from '../store/serviceStore'

const { Sider, Header, Content } = AntLayout

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/llm', icon: <RobotOutlined />, label: '模型配置' },
  { key: '/security', icon: <SafetyOutlined />, label: '安全设置' },
  { key: '/limits', icon: <StopOutlined />, label: '行为限制' },
  { key: '/workspace', icon: <FolderOutlined />, label: '工作区' },
  { key: '/memory', icon: <SearchOutlined />, label: '记忆检索' },
  { key: '/tools', icon: <ToolOutlined />, label: '工具配置' },
  { key: '/tool-registry', icon: <ApiOutlined />, label: '工具注册表' },
  { key: '/prompts', icon: <FormOutlined />, label: '提示词' },
  { key: '/scenarios', icon: <AppstoreOutlined />, label: 'Skill 管理' },
  { key: '/system', icon: <ControlOutlined />, label: '系统控制' },
]

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { status } = useServiceStore()
  const { token } = theme.useToken()

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="dark"
        style={{ overflow: 'auto', height: '100vh', position: 'fixed', left: 0, top: 0, bottom: 0 }}
      >
        <div style={{
          height: 48,
          margin: 12,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#fff',
          fontSize: collapsed ? 16 : 18,
          fontWeight: 700,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
        }}>
          {collapsed ? 'WC' : 'WeChat Claude'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <AntLayout style={{ marginLeft: collapsed ? 80 : 200, transition: 'margin-left 0.2s' }}>
        <Header style={{
          padding: '0 24px',
          background: token.colorBgContainer,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          height: 48,
          lineHeight: '48px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: status?.running ? '#52c41a' : '#ff4d4f',
            }} />
            <span style={{ fontSize: 13, color: token.colorTextSecondary }}>
              {status?.running ? '运行中' : '已停止'}
            </span>
          </div>
        </Header>
        <Content style={{ margin: 16, padding: 24, background: token.colorBgContainer, borderRadius: token.borderRadiusLG, minHeight: 280 }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  )
}
