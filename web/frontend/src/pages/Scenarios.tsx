import { useEffect, useState } from 'react'
import { Card, Table, Tag, Button, Space, message, Spin, Modal, Form, Input, Switch, List, Select, Popconfirm, Alert, Empty, Divider, Tooltip } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, InfoCircleOutlined, RobotOutlined } from '@ant-design/icons'
import api, { generateSkill } from '../api/client'

interface SkillAction {
  tool: string
  args: Record<string, any>
}

interface SkillMeta {
  name: string
  type: string
  description: string
  version: string
  author: string
  tags: string[]
  enabled: boolean
  source_path: string
  triggers: string[]
  actions?: SkillAction[]
}

const toolOptions = [
  { value: 'open_app', label: 'open_app - 打开应用' },
  { value: 'system_action', label: 'system_action - 系统操作' },
  { value: 'run_shell', label: 'run_shell - 执行命令' },
  { value: 'send_file', label: 'send_file - 发送文件' },
]

const toolArgExamples: Record<string, string> = {
  open_app: '{"app_name": "code"}',
  system_action: '{"action": "volume_down"}',
  run_shell: '{"command": "dir"}',
  send_file: '{"file_path": "workspace/output/result.txt"}',
}

export default function Scenarios() {
  const [skills, setSkills] = useState<SkillMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [currentSkill, setCurrentSkill] = useState<SkillMeta | null>(null)
  const [form] = Form.useForm()
  const [actions, setActions] = useState<SkillAction[]>([])
  const [triggers, setTriggers] = useState<string[]>([])
  const [generateModalOpen, setGenerateModalOpen] = useState(false)
  const [generateDesc, setGenerateDesc] = useState('')
  const [generating, setGenerating] = useState(false)

  const fetchSkills = async () => {
    setLoading(true)
    try {
      const resp = await api.get('/skills')
      setSkills(resp.data)
    } catch {
      message.error('获取 Skill 列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSkills()
  }, [])

  const openEditModal = (skill: SkillMeta | null) => {
    setCurrentSkill(skill)
    if (skill) {
      form.setFieldsValue({
        name: skill.name,
        description: skill.description,
        version: skill.version,
        author: skill.author,
        enabled: skill.enabled,
      })
      setTriggers(skill.triggers || [])
      setActions(skill.actions || [])
    } else {
      form.resetFields()
      form.setFieldsValue({ version: '1.0.0', enabled: true })
      setTriggers([])
      setActions([])
    }
    setEditModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const skillData = {
        ...values,
        type: 'skill',
        triggers,
        actions,
      }

      if (currentSkill) {
        await api.put(`/skills/${currentSkill.name}`, skillData)
        message.success('Skill 更新成功')
      } else {
        await api.post('/skills', skillData)
        message.success('Skill 创建成功')
      }

      setEditModalOpen(false)
      fetchSkills()
    } catch {
      message.error('保存失败')
    }
  }

  const handleDelete = async (name: string) => {
    try {
      await api.delete(`/skills/${name}`)
      message.success('Skill 删除成功')
      fetchSkills()
    } catch {
      message.error('删除失败')
    }
  }

  const handleToggleEnabled = async (name: string, enabled: boolean) => {
    try {
      await api.put(`/tools/${name}/enable`, null, { params: { enabled } })
      message.success(`${enabled ? '启用' : '禁用'}成功`)
      fetchSkills()
    } catch {
      message.error('操作失败')
    }
  }

  const handleGenerate = async () => {
    if (!generateDesc.trim()) {
      message.warning('请输入描述')
      return
    }
    setGenerating(true)
    try {
      const result = await generateSkill({ description: generateDesc })
      const skill = result.skill
      if (skill) {
        setCurrentSkill({ name: skill.name, type: 'skill', description: skill.description || '', version: '1.0.0', author: '', tags: [], enabled: true, source_path: '', triggers: skill.triggers || [], actions: skill.actions || [] })
        form.resetFields()
        form.setFieldsValue({
          name: skill.name || '',
          description: skill.description || '',
          version: '1.0.0',
          enabled: true,
        })
        setTriggers(skill.triggers || [])
        setActions(skill.actions || [])
        setGenerateModalOpen(false)
        setGenerateDesc('')
        setEditModalOpen(true)
        message.success('模板生成成功，请检查并调整后保存')
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail || '生成失败'
      message.error(detail)
    } finally {
      setGenerating(false)
    }
  }

  const addAction = () => {
    setActions([...actions, { tool: 'open_app', args: {} }])
  }

  const removeAction = (index: number) => {
    setActions(actions.filter((_, i) => i !== index))
  }

  const updateAction = (index: number, field: string, value: any) => {
    const newActions = [...actions]
    if (field === 'tool') {
      newActions[index] = { tool: value, args: {} }
    } else {
      newActions[index].args = { ...newActions[index].args, [field]: value }
    }
    setActions(newActions)
  }

  const addTrigger = () => {
    setTriggers([...triggers, ''])
  }

  const removeTrigger = (index: number) => {
    setTriggers(triggers.filter((_, i) => i !== index))
  }

  const updateTrigger = (index: number, value: string) => {
    const newTriggers = [...triggers]
    newTriggers[index] = value
    setTriggers(newTriggers)
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <code>{name}</code>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '触发器',
      dataIndex: 'triggers',
      key: 'triggers',
      render: (triggers: string[]) => (
        <Space size={4} wrap>
          {triggers?.slice(0, 3).map((t, i) => <Tag key={i} color="purple">{t}</Tag>)}
          {triggers?.length > 3 && <Tag>+{triggers.length - 3}</Tag>}
        </Space>
      ),
    },
    {
      title: '动作数',
      key: 'actions_count',
      width: 80,
      render: (_: any, record: SkillMeta) => <Tag>{record.actions?.length || 0}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record: SkillMeta) => (
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
      width: 120,
      render: (_: any, record: SkillMeta) => (
        <Space>
          <Button type="text" icon={<EditOutlined />} onClick={() => openEditModal(record)} />
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.name)}>
            <Button type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="Skill 是可触发的自动化任务。当用户说触发词时，会依次执行预设的动作。Skill 保存在 tools/skills/ 目录下。"
        />

        <Card
          title={`Skill 管理 (${skills.length} 个)`}
          extra={
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchSkills}>刷新</Button>
              <Button icon={<RobotOutlined />} onClick={() => { setGenerateDesc(''); setGenerateModalOpen(true) }}>
                AI 生成
              </Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditModal(null)}>
                新建 Skill
              </Button>
            </Space>
          }
        >
          <Table
            dataSource={skills}
            columns={columns}
            rowKey="name"
            pagination={{ pageSize: 10 }}
            size="small"
          />
        </Card>

        <Modal
          title="AI 生成 Skill 模板"
          open={generateModalOpen}
          onCancel={() => setGenerateModalOpen(false)}
          onOk={handleGenerate}
          okText="生成"
          cancelText="取消"
          centered
          confirmLoading={generating}
          width={520}
        >
          <div style={{ marginBottom: 12, color: '#666', fontSize: 13 }}>
            描述你想实现的 Skill 功能，AI 将自动生成匹配的触发器和动作模板。生成后可进一步编辑调整。
          </div>
          <Input.TextArea
            value={generateDesc}
            onChange={e => setGenerateDesc(e.target.value)}
            placeholder="如：我想创建一个工作模式，当我说'开始工作'时，打开 VS Code 和浏览器，并搜索今日待办"
            rows={4}
            autoFocus
          />
          <div style={{ marginTop: 8, color: '#999', fontSize: 12 }}>
            可用工具：open_app（打开应用）、system_action（系统操作）、run_shell（执行命令）、send_file（发送文件）
          </div>
        </Modal>

        <Modal
          title={currentSkill ? `编辑 Skill: ${currentSkill.name}` : '新建 Skill'}
          open={editModalOpen}
          onCancel={() => setEditModalOpen(false)}
          onOk={handleSave}
          width={720}
          okText="保存"
          cancelText="取消"
          centered
          styles={{ body: { maxHeight: 'calc(80vh - 120px)', overflowY: 'auto', paddingRight: 4 } }}
        >
          <Form form={form} layout="vertical">
            <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入 Skill 名称' }]}>
              <Input placeholder="如 work_mode、learning_mode" disabled={!!currentSkill} />
            </Form.Item>

            <Form.Item label="描述" name="description">
              <Input placeholder="如 工作模式 - 打开工作相关应用" />
            </Form.Item>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <Form.Item label="版本" name="version">
                <Input placeholder="1.0.0" />
              </Form.Item>

              <Form.Item label="作者" name="author">
                <Input placeholder="作者名称" />
              </Form.Item>
            </div>

            <Form.Item label="启用" name="enabled" valuePropName="checked">
              <Switch />
            </Form.Item>

            <Divider style={{ margin: '16px 0' }} />

            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontWeight: 500 }}>触发器</span>
                <Tooltip title="用户说这些词时触发 Skill">
                  <InfoCircleOutlined style={{ color: '#999' }} />
                </Tooltip>
              </div>
              <div style={{ color: '#888', fontSize: 13, marginBottom: 12 }}>
                当用户消息中包含以下关键词时，会自动触发此 Skill
              </div>
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                {triggers.map((t, i) => (
                  <Space key={i} style={{ width: '100%' }}>
                    <Input
                      value={t}
                      onChange={e => updateTrigger(i, e.target.value)}
                      placeholder="如 进入工作模式"
                      style={{ width: 320 }}
                    />
                    <Button type="text" danger icon={<DeleteOutlined />} onClick={() => removeTrigger(i)} />
                  </Space>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={addTrigger} style={{ width: 320 }}>
                  添加触发器
                </Button>
              </Space>
            </div>

            <Divider style={{ margin: '16px 0' }} />

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontWeight: 500 }}>动作列表</span>
                <Tooltip title="触发后依次执行的工具">
                  <InfoCircleOutlined style={{ color: '#999' }} />
                </Tooltip>
              </div>
              <div style={{ color: '#888', fontSize: 13, marginBottom: 12 }}>
                触发后按顺序执行以下动作，每个动作对应一个工具调用
              </div>
              {actions.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="暂无动作"
                  style={{ marginBottom: 16 }}
                />
              ) : (
                <List
                  dataSource={actions}
                  renderItem={(action, i) => (
                    <List.Item style={{ padding: '12px 0', borderBottom: '1px solid #f0f0f0' }}>
                      <Space direction="vertical" style={{ width: '100%' }} size="middle">
                        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                          <Space>
                            <Tag color="blue">步骤 {i + 1}</Tag>
                            <Select
                              value={action.tool}
                              onChange={v => updateAction(i, 'tool', v)}
                              options={toolOptions}
                              style={{ width: 200 }}
                            />
                          </Space>
                          <Button type="text" danger icon={<DeleteOutlined />} onClick={() => removeAction(i)}>
                            删除
                          </Button>
                        </Space>
                        <div>
                          <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>
                            参数 (JSON 格式)
                            <span style={{ color: '#999', marginLeft: 8 }}>
                              示例: {toolArgExamples[action.tool] || '{}'}
                            </span>
                          </div>
                          <Input.TextArea
                            value={JSON.stringify(action.args, null, 2)}
                            onChange={e => {
                              try {
                                const args = JSON.parse(e.target.value)
                                updateAction(i, 'args', args)
                              } catch {}
                            }}
                            placeholder={`${toolArgExamples[action.tool] || '{}'} `}
                            rows={3}
                            style={{ fontFamily: 'monospace', fontSize: 13 }}
                          />
                        </div>
                      </Space>
                    </List.Item>
                  )}
                />
              )}
              <Button type="dashed" icon={<PlusOutlined />} onClick={addAction} style={{ marginTop: 8, width: '100%' }}>
                添加动作
              </Button>
            </div>
          </Form>
        </Modal>
      </Space>
    </Spin>
  )
}
