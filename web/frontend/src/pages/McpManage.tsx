import { useEffect, useState } from 'react'
import { Card, Table, Button, Tag, Switch, Space, Typography, message, Popconfirm, Spin, Descriptions, Alert, Badge } from 'antd'
import { ApiOutlined, LinkOutlined, DisconnectOutlined, ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { getMcpStatus, getMcpTools, connectMcpServer, disconnectMcpServer, toggleMcp } from '../api/client'

const { Title, Text } = Typography

interface McpStatus {
  enabled: boolean
  servers_count: number
  connected_count: number
  servers: McpServer[]
}

interface McpServer {
  name: string
  status: string
  transport: string
  tools_count: number
}

interface McpTool {
  name: string
  server: string
  description: string
}

const statusIcon: Record<string, React.ReactNode> = {
  connected: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
  disconnected: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
}

export default function McpManage() {
  const [status, setStatus] = useState<McpStatus | null>(null)
  const [servers, setServers] = useState<McpServer[]>([])
  const [tools, setTools] = useState<McpTool[]>([])
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [toggling, setToggling] = useState(false)

  const fetchAll = async () => {
    try {
      setLoading(true)
      const [statusData, toolsData] = await Promise.all([
        getMcpStatus(),
        getMcpTools(),
      ])
      setStatus(statusData)
      setServers(statusData?.servers || [])
      setTools(toolsData?.tools || [])
    } catch {
      message.error('获取 MCP 状态失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAll()
  }, [])

  const handleToggle = async (checked: boolean) => {
    try {
      setToggling(true)
      await toggleMcp(checked)
      message.success(checked ? 'MCP 已启用' : 'MCP 已禁用')
      fetchAll()
    } catch {
      message.error('切换 MCP 状态失败')
    } finally {
      setToggling(false)
    }
  }

  const handleConnect = async (name: string) => {
    try {
      setActionLoading(name)
      const result = await connectMcpServer(name)
      if (result.success) {
        const toolCount = Array.isArray(result.tools_loaded) ? result.tools_loaded.length : 0
        message.success(`${name} 已连接，加载了 ${toolCount} 个工具`)
      } else {
        message.error(`${name} 连接失败: ${result.error || '未知错误'}`)
      }
      fetchAll()
    } catch {
      message.error(`${name} 连接异常`)
    } finally {
      setActionLoading(null)
    }
  }

  const handleDisconnect = async (name: string) => {
    try {
      setActionLoading(name)
      const result = await disconnectMcpServer(name)
      if (result.success) {
        message.success(`${name} 已断开`)
      } else {
        message.error(`${name} 断开失败: ${result.error || '未知错误'}`)
      }
      fetchAll()
    } catch {
      message.error(`${name} 断开异常`)
    } finally {
      setActionLoading(null)
    }
  }

  const serverColumns = [
    {
      title: '服务名称',
      dataIndex: 'name',
      key: 'name',
      render: (v: string) => <Tag icon={<ApiOutlined />} color="blue">{v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => (
        <Space>
          {statusIcon[v] || null}
          <Badge
            status={v === 'connected' ? 'success' : v === 'disconnected' ? 'error' : 'default'}
            text={v === 'connected' ? '已连接' : v === 'disconnected' ? '未连接' : v}
          />
        </Space>
      ),
    },
    {
      title: '传输方式',
      dataIndex: 'transport',
      key: 'transport',
      render: (v: string) => <Tag>{v || 'stdio'}</Tag>,
    },
    {
      title: '已加载工具',
      dataIndex: 'tools_count',
      key: 'tools_count',
      render: (v: number) => (
        <Tag color={v > 0 ? 'green' : 'default'}>{v ?? 0} 个</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: unknown, record: McpServer) => (
        <Space>
          {record.status === 'connected' ? (
            <Popconfirm
              title={`确定断开 ${record.name}? 断开后该服务的工具将不可用`}
              onConfirm={() => handleDisconnect(record.name)}
              okText="确定断开"
              cancelText="取消"
            >
              <Button
                size="small"
                danger
                icon={<DisconnectOutlined />}
                loading={actionLoading === record.name}
              >
                断开连接
              </Button>
            </Popconfirm>
          ) : (
            <Button
              size="small"
              type="primary"
              icon={<LinkOutlined />}
              onClick={() => handleConnect(record.name)}
              loading={actionLoading === record.name}
            >
              连接
            </Button>
          )}
        </Space>
      ),
    },
  ]

  const toolColumns = [
    {
      title: '工具名称',
      dataIndex: 'name',
      key: 'name',
      render: (v: string) => <Tag color="cyan">{v}</Tag>,
    },
    {
      title: '所属服务',
      dataIndex: 'server',
      key: 'server',
      render: (v: string) => v ? <Tag color="blue">{v}</Tag> : <Text type="secondary">-</Text>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (v: string) => v || <Text type="secondary">-</Text>,
    },
  ]

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Title level={4} style={{ margin: 0 }}>
          <ApiOutlined style={{ marginRight: 8 }} />
          MCP 管理
        </Title>

        <Alert
          message="MCP 是什么？"
          description="MCP（Model Context Protocol）是 Agent 调用外部工具/服务的协议。连接 MCP Server 后，Agent 就能直接调用地图、搜索等外部 API。简单说：MCP = Agent 调工具（纵向连接）。飞书已内置为原生工具，无需 MCP。"
          type="info"
          showIcon
          closable
        />

        <Card
          title="MCP 状态"
          size="small"
          extra={
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchAll} size="small">
                刷新
              </Button>
            </Space>
          }
        >
          <Descriptions column={3} size="small">
            <Descriptions.Item label="MCP 总开关">
              <Switch
                checked={status?.enabled ?? false}
                onChange={handleToggle}
                loading={toggling}
                checkedChildren="开"
                unCheckedChildren="关"
              />
            </Descriptions.Item>
            <Descriptions.Item label="已配置服务">
              <Tag color="blue">{status?.servers_count ?? 0}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="已连接服务">
              <Tag color="green">{status?.connected_count ?? 0}</Tag>
            </Descriptions.Item>
          </Descriptions>
        </Card>

        <Card title="MCP 服务列表" size="small">
          {servers.length === 0 ? (
            <Alert
              message="暂无配置的 MCP 服务"
              description="请在 config.yaml 的 mcp.servers 中添加服务配置"
              type="warning"
              showIcon
            />
          ) : (
            <Table
              columns={serverColumns}
              dataSource={servers}
              rowKey={(r) => r.name}
              size="small"
              pagination={false}
            />
          )}
        </Card>

        <Card
          title={`可用工具 (${tools.length})`}
          size="small"
        >
          {tools.length === 0 ? (
            <Alert
              message="暂无已加载的 MCP 工具"
              description="请先连接 MCP 服务，工具会自动加载"
              type="warning"
              showIcon
            />
          ) : (
            <Table
              columns={toolColumns}
              dataSource={tools}
              rowKey={(r) => `${r.server}-${r.name}`}
              size="small"
              pagination={{ pageSize: 10 }}
            />
          )}
        </Card>
      </Space>
    </Spin>
  )
}
