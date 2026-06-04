import { useEffect, useState } from 'react'
import { Card, Table, Button, Tag, Space, Typography, message, Spin, Descriptions, Alert, Badge, Tooltip, Popconfirm } from 'antd'
import { CloudServerOutlined, ReloadOutlined, LinkOutlined, ExperimentOutlined, FileOutlined, TableOutlined, ToolOutlined, DeleteOutlined } from '@ant-design/icons'
import { getFeishuStatus, testFeishuConnection, getFeishuDocuments, getFeishuBitables, deleteFeishuDocument } from '../api/client'

const { Title, Text } = Typography

interface FeishuStatus {
  configured: boolean
  feishu_domain: string
  token_ok: boolean
  token_error: string
  tools_count: number
  tools: FeishuTool[]
}

interface FeishuTool {
  name: string
  description: string
  parameters: Record<string, any>
  required: string[]
}

interface FeishuFile {
  token: string
  name: string
  type: string
  url: string
  last_modified: string
}

// 文件类型 → URL 路径映射
const FILE_TYPE_PATH: Record<string, string> = {
  docx: 'docx',
  doc: 'docs',
  bitable: 'base',
  sheet: 'sheets',
  folder: 'drive/folder',
  mindnote: 'mindnote',
  slide: 'slides',
  file: 'file',
}

export default function FeishuManage() {
  const [status, setStatus] = useState<FeishuStatus | null>(null)
  const [documents, setDocuments] = useState<FeishuFile[]>([])
  const [bitables, setBitables] = useState<FeishuFile[]>([])
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<any>(null)
  const [deleting, setDeleting] = useState<string | null>(null)

  const feishuDomain = status?.feishu_domain || 'feishu'

  const buildFileUrl = (record: FeishuFile): string => {
    if (record.url) return record.url
    const path = FILE_TYPE_PATH[record.type] || 'docx'
    return `https://${feishuDomain}.feishu.cn/${path}/${record.token}`
  }

  const fetchAll = async () => {
    try {
      setLoading(true)
      const [statusData, docsData, bitableData] = await Promise.all([
        getFeishuStatus(),
        getFeishuDocuments(),
        getFeishuBitables(),
      ])
      setStatus(statusData)
      setDocuments(docsData?.files || [])
      setBitables(bitableData?.bitables || [])
    } catch {
      message.error('获取飞书状态失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAll()
  }, [])

  const handleTest = async () => {
    try {
      setTesting(true)
      setTestResult(null)
      const result = await testFeishuConnection()
      setTestResult(result)
      if (result.success) {
        message.success('飞书 API 连接测试成功')
      } else {
        message.error(`连接测试失败: ${result.error || '未知错误'}`)
      }
    } catch {
      message.error('连接测试异常')
    } finally {
      setTesting(false)
    }
  }

  const handleDelete = async (fileToken: string, fileType: string, name: string) => {
    try {
      setDeleting(fileToken)
      const result = await deleteFeishuDocument(fileToken, fileType)
      if (result.success) {
        message.success(`"${name}" 已删除（移入回收站）`)
        fetchAll()
      } else {
        message.error(`删除失败: ${result.error || '未知错误'}`)
      }
    } catch {
      message.error('删除请求异常')
    } finally {
      setDeleting(null)
    }
  }

  const fileTypeMap: Record<string, { label: string; color: string }> = {
    doc: { label: '文档', color: 'blue' },
    docx: { label: '文档', color: 'blue' },
    sheet: { label: '表格', color: 'green' },
    bitable: { label: '多维表格', color: 'purple' },
    file: { label: '文件', color: 'orange' },
    folder: { label: '文件夹', color: 'default' },
    slide: { label: '幻灯片', color: 'cyan' },
    wiki: { label: '知识库', color: 'geekblue' },
  }

  const toolColumns = [
    {
      title: '工具名称',
      dataIndex: 'name',
      key: 'name',
      render: (v: string) => <Tag color="cyan">{v}</Tag>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (v: string) => v || <Text type="secondary">-</Text>,
    },
  ]

  const docColumns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 120,
      render: (v: string) => {
        const info = fileTypeMap[v] || { label: v, color: 'default' }
        return <Tag color={info.color}>{info.label}</Tag>
      },
    },
    {
      title: 'Token',
      dataIndex: 'token',
      key: 'token',
      width: 180,
      render: (v: string) => (
        <Tooltip title={v}>
          <Text copyable={{ text: v }} style={{ fontSize: 12 }}>
            {v.length > 16 ? `${v.slice(0, 8)}...${v.slice(-8)}` : v}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_: unknown, record: FeishuFile) => (
        <Space>
          <Button
            size="small"
            type="link"
            icon={<LinkOutlined />}
            href={buildFileUrl(record)}
            target="_blank"
          >
            打开
          </Button>
          {record.type !== 'folder' && (
            <Popconfirm
              title={`确定删除"${record.name}"吗？`}
              description="删除后可在飞书回收站恢复"
              onConfirm={() => handleDelete(record.token, record.type, record.name)}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button
                size="small"
                type="link"
                danger
                icon={<DeleteOutlined />}
                loading={deleting === record.token}
              >
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const bitableColumns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: 'Token',
      dataIndex: 'token',
      key: 'token',
      width: 180,
      render: (v: string) => (
        <Tooltip title={v}>
          <Text copyable={{ text: v }} style={{ fontSize: 12 }}>
            {v.length > 16 ? `${v.slice(0, 8)}...${v.slice(-8)}` : v}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_: unknown, record: FeishuFile) => (
        <Space>
          <Button
            size="small"
            type="link"
            icon={<LinkOutlined />}
            href={buildFileUrl(record)}
            target="_blank"
          >
            打开
          </Button>
          <Popconfirm
            title={`确定删除"${record.name}"吗？`}
            description="删除后可在飞书回收站恢复"
            onConfirm={() => handleDelete(record.token, 'bitable', record.name)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button
              size="small"
              type="link"
              danger
              icon={<DeleteOutlined />}
              loading={deleting === record.token}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Title level={4} style={{ margin: 0 }}>
          <CloudServerOutlined style={{ marginRight: 8 }} />
          飞书工作台
        </Title>

        <Alert
          message="飞书集成说明"
          description="使用 tenant_access_token（应用身份）创建的文档归属应用云空间，不在你的个人云盘中。通过下方列表可查看、跳转和删除这些文档。如需文档出现在个人云盘，需配置 user_access_token（OAuth 授权）。"
          type="info"
          showIcon
          closable
        />

        {/* 状态卡片 */}
        <Card
          title="连接状态"
          size="small"
          extra={
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchAll} size="small">
                刷新
              </Button>
              <Button
                icon={<ExperimentOutlined />}
                onClick={handleTest}
                loading={testing}
                size="small"
                type="primary"
                ghost
              >
                测试连接
              </Button>
            </Space>
          }
        >
          <Descriptions column={4} size="small">
            <Descriptions.Item label="配置状态">
              {status?.configured ? (
                <Badge status="success" text="已配置" />
              ) : (
                <Badge status="error" text="未配置" />
              )}
            </Descriptions.Item>
            <Descriptions.Item label="Token 状态">
              {status?.token_ok ? (
                <Badge status="success" text="有效" />
              ) : (
                <Tooltip title={status?.token_error || '未获取'}>
                  <Badge status="error" text="无效" />
                </Tooltip>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="已注册工具">
              <Tag color="cyan">{status?.tools_count ?? 0} 个</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="官方后台">
              <Button
                size="small"
                type="link"
                icon={<LinkOutlined />}
                href="https://open.feishu.cn/app"
                target="_blank"
              >
                飞书开发者后台
              </Button>
            </Descriptions.Item>
          </Descriptions>
          {testResult && (
            <Alert
              style={{ marginTop: 12 }}
              message={testResult.success ? '连接测试通过' : '连接测试失败'}
              description={
                testResult.success
                  ? `Token 有效${testResult.drive_ok ? '，云空间可访问' : '，但云空间访问受限（可能缺少 drive 权限）'}`
                  : testResult.error || testResult.warning || '未知错误'
              }
              type={testResult.success ? 'success' : 'error'}
              showIcon
              closable
            />
          )}
        </Card>

        {/* 快捷入口 */}
        <Card title="快捷入口" size="small">
          <Space size="middle" wrap>
            <Button
              icon={<LinkOutlined />}
              href="https://open.feishu.cn/app"
              target="_blank"
            >
              飞书开发者后台
            </Button>
            <Button
              icon={<FileOutlined />}
              href={`https://${feishuDomain}.feishu.cn/drive/home/`}
              target="_blank"
            >
              飞书云文档
            </Button>
            <Button
              icon={<TableOutlined />}
              href={`https://${feishuDomain}.feishu.cn/base/home/`}
              target="_blank"
            >
              飞书多维表格
            </Button>
            <Button
              icon={<CloudServerOutlined />}
              href="https://open.feishu.cn/document/server-docs/api-call-guide/calling-process/overview"
              target="_blank"
            >
              API 文档
            </Button>
          </Space>
        </Card>

        {/* 应用云空间文件 */}
        <Card
          title={
            <Space>
              <FileOutlined />
              <span>应用云空间文件 ({documents.length})</span>
            </Space>
          }
          size="small"
        >
          {documents.length === 0 ? (
            <Alert
              message="应用云空间暂无文件"
              description="通过 AI 助手创建的文档/表格会出现在这里。也可能缺少云空间访问权限，请点击「测试连接」检查。"
              type="warning"
              showIcon
            />
          ) : (
            <Table
              columns={docColumns}
              dataSource={documents}
              rowKey={(r) => r.token}
              size="small"
              pagination={{ pageSize: 10 }}
            />
          )}
        </Card>

        {/* 多维表格 */}
        <Card
          title={
            <Space>
              <TableOutlined />
              <span>多维表格 ({bitables.length})</span>
            </Space>
          }
          size="small"
        >
          {bitables.length === 0 ? (
            <Text type="secondary">暂无多维表格</Text>
          ) : (
            <Table
              columns={bitableColumns}
              dataSource={bitables}
              rowKey={(r) => r.token}
              size="small"
              pagination={{ pageSize: 10 }}
            />
          )}
        </Card>

        {/* 已注册工具 */}
        <Card
          title={
            <Space>
              <ToolOutlined />
              <span>已注册飞书工具 ({status?.tools_count ?? 0})</span>
            </Space>
          }
          size="small"
        >
          {(!status?.tools || status.tools.length === 0) ? (
            <Alert
              message="暂无飞书工具"
              description="请确认 tools/builtin/feishu.py 已正确加载"
              type="warning"
              showIcon
            />
          ) : (
            <Table
              columns={toolColumns}
              dataSource={status?.tools || []}
              rowKey={(r) => r.name}
              size="small"
              pagination={{ pageSize: 10 }}
            />
          )}
        </Card>
      </Space>
    </Spin>
  )
}
