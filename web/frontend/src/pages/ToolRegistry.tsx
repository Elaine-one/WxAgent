import { useEffect, useState } from 'react'
import { Card, Table, Tag, Button, Space, message, Spin, Statistic, Row, Col, Switch, Modal, Descriptions } from 'antd'
import { ReloadOutlined, InfoCircleOutlined } from '@ant-design/icons'
import api from '../api/client'

interface ToolMeta {
  name: string
  type: string
  description: string
  version: string
  author: string
  tags: string[]
  enabled: boolean
  priority: number
  source_path: string
  triggers: string[]
}

interface ToolStats {
  total: number
  enabled: number
  disabled: number
  by_type: Record<string, number>
}

const typeColors: Record<string, string> = {
  builtin: 'blue',
  skill: 'green',
  mode: 'purple',
  mcp: 'orange',
  external: 'cyan',
}

export default function ToolRegistry() {
  const [tools, setTools] = useState<ToolMeta[]>([])
  const [stats, setStats] = useState<ToolStats | null>(null)
  const [types, setTypes] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedTool, setSelectedTool] = useState<ToolMeta | null>(null)
  const [filterType, setFilterType] = useState<string | null>(null)

  const fetchTools = async () => {
    setLoading(true)
    try {
      const [toolsRes, statsRes, typesRes] = await Promise.all([
        api.get('/tools', { params: { type: filterType } }).then(r => r.data),
        api.get('/tools/stats').then(r => r.data),
        api.get('/tools/types').then(r => r.data),
      ])
      setTools(toolsRes)
      setStats(statsRes)
      setTypes(typesRes)
    } catch {
      message.error('获取工具列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTools()
  }, [filterType])

  const handleToggleEnabled = async (name: string, enabled: boolean) => {
    try {
      await api.put(`/tools/${name}/enable`, null, { params: { enabled } })
      message.success(`${enabled ? '启用' : '禁用'}工具 ${name}`)
      fetchTools()
    } catch {
      message.error('操作失败')
    }
  }

  const handleReload = async () => {
    try {
      await api.post('/tools/reload')
      message.success('工具已重新加载')
      fetchTools()
    } catch {
      message.error('重新加载失败')
    }
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: ToolMeta) => {
        const displayName = record.type === 'skill' ? name.replace(/^skill_/, '') : name
        return <code>{displayName}</code>
      },
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => <Tag color={typeColors[type] || 'default'}>{type}</Tag>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (desc: string) => desc?.replace(/^\[Skill\] /, '').replace(/^\[Mode\] /, ''),
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 80,
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record: ToolMeta) => (
        <Switch
          size="small"
          checked={enabled}
          onChange={(checked) => handleToggleEnabled(record.name, checked)}
        />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: any, record: ToolMeta) => (
        <Button
          type="text"
          icon={<InfoCircleOutlined />}
          onClick={() => setSelectedTool(record)}
        />
      ),
    },
  ]

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {stats && (
          <Row gutter={16}>
            <Col span={6}>
              <Card>
                <Statistic title="总工具数" value={stats.total} />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic title="已启用" value={stats.enabled} valueStyle={{ color: '#3f8600' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic title="已禁用" value={stats.disabled} valueStyle={{ color: '#cf1322' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="内置工具"
                  value={stats.by_type.builtin || 0}
                  suffix={`/ ${stats.by_type.skill || 0} Skills / ${stats.by_type.mcp || 0} MCP`}
                />
              </Card>
            </Col>
          </Row>
        )}

        <Card
          title="工具注册表"
          extra={
            <Space>
              <Tag
                color={filterType === null ? 'blue' : 'default'}
                style={{ cursor: 'pointer' }}
                onClick={() => setFilterType(null)}
              >
                全部
              </Tag>
              {types.map(t => (
                <Tag
                  key={t}
                  color={filterType === t ? 'blue' : 'default'}
                  style={{ cursor: 'pointer' }}
                  onClick={() => setFilterType(t === filterType ? null : t)}
                >
                  {t}
                </Tag>
              ))}
              <Button icon={<ReloadOutlined />} onClick={handleReload}>
                重新加载
              </Button>
            </Space>
          }
        >
          <Table
            dataSource={tools}
            columns={columns}
            rowKey="name"
            pagination={{ pageSize: 20 }}
            size="small"
          />
        </Card>

        <Modal
          title={selectedTool?.name}
          open={!!selectedTool}
          onCancel={() => setSelectedTool(null)}
          footer={null}
          width={600}
        >
          {selectedTool && (
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="类型">
                <Tag color={typeColors[selectedTool.type] || 'default'}>{selectedTool.type}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="版本">{selectedTool.version}</Descriptions.Item>
              <Descriptions.Item label="作者">{selectedTool.author || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={selectedTool.enabled ? 'green' : 'red'}>
                  {selectedTool.enabled ? '启用' : '禁用'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>
                {selectedTool.description || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="标签" span={2}>
                {selectedTool.tags.length > 0
                  ? selectedTool.tags.map(t => <Tag key={t}>{t}</Tag>)
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="触发器" span={2}>
                {selectedTool.triggers.length > 0
                  ? selectedTool.triggers.map(t => <Tag key={t} color="purple">{t}</Tag>)
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="来源路径" span={2}>
                <code style={{ fontSize: 12 }}>{selectedTool.source_path || '-'}</code>
              </Descriptions.Item>
            </Descriptions>
          )}
        </Modal>
      </Space>
    </Spin>
  )
}
