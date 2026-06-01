import { useEffect, useState } from 'react'
import { Switch, InputNumber, Checkbox, Button, Card, Space, message, Spin, Typography, Alert, Select, Tooltip } from 'antd'
import { SaveOutlined, EditOutlined, CloseOutlined } from '@ant-design/icons'
import { useConfigStore } from '../store/configStore'
import { getConfig } from '../api/client'
import { useEditMode } from '../hooks/useEditMode'
import TagList from '../components/TagList'

const { Text } = Typography

export default function Security() {
  const { config, loading, saving, fetchConfig, updateConfig } = useConfigStore()
  const { editing, startEdit, cancelEdit, saveAndExit } = useEditMode()
  const [form, setForm] = useState<Record<string, any>>({})
  const [modelOptions, setModelOptions] = useState<{ value: string; label: string }[]>([])

  useEffect(() => {
    fetchConfig('security')
    Promise.all([
      getConfig('llm'),
      getConfig('router'),
    ]).then(([llmConfig, routerConfig]: [any, any]) => {
      const models = new Set<string>()
      if (llmConfig.model) models.add(llmConfig.model)
      if (llmConfig.vision_model) models.add(llmConfig.vision_model)
      if (llmConfig.fallback_model) models.add(llmConfig.fallback_model)
      if (routerConfig.default) models.add(routerConfig.default)
      if (routerConfig.routes) {
        Object.values(routerConfig.routes).forEach((route: any) => {
          if (route?.model) models.add(route.model)
        })
      }
      if (routerConfig.task_overrides) {
        Object.values(routerConfig.task_overrides).forEach((override: any) => {
          if (override?.model) models.add(override.model)
        })
      }
      const options = Array.from(models).filter(m => m).map(m => ({ value: m, label: m }))
      setModelOptions(options)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (config && Object.keys(config).length > 0 && !editing) {
      setForm(config)
    }
  }, [config, editing])

  const set = (key: string, value: any) => setForm(prev => ({ ...prev, [key]: value }))
  const setNested = (path: string[], value: any) => {
    setForm(prev => {
      const next = { ...prev }
      let obj: any = next
      for (let i = 0; i < path.length - 1; i++) {
        obj[path[i]] = { ...(obj[path[i]] ?? {}) }
        obj = obj[path[i]]
      }
      obj[path[path.length - 1]] = value
      return next
    })
  }

  const handleSave = async () => {
    try {
      await updateConfig('security', form)
      message.success('保存成功')
    } catch {
      message.error('保存失败')
    }
  }

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="安全设置控制 Agent 的行为边界。风险级别决定哪些命令需要用户确认，路径沙箱限制 Agent 可访问的目录。"
        />

        <Card title="基础设置">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>开发者模式</span>
                <Tooltip title="开启后允许执行更多系统操作，适合开发调试">
                  <Switch checked={form.dev_mode ?? false} onChange={v => set('dev_mode', v)} disabled={!editing} />
                </Tooltip>
              </div>
              <Text type="secondary" style={{ fontSize: 12 }}>开启后允许执行更多系统操作，适合开发调试</Text>
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>AI 审查器</span>
                <Tooltip title="让 AI 在执行命令前进行安全审查">
                  <Switch checked={form.ai_reviewer?.enabled ?? false} onChange={v => setNested(['ai_reviewer', 'enabled'], v)} disabled={!editing} />
                </Tooltip>
              </div>
              <Text type="secondary" style={{ fontSize: 12 }}>让 AI 在执行命令前进行安全审查，判断是否需要用户确认</Text>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>AI 审查器模型</label>
              <Select
                value={form.ai_reviewer?.model ?? ''}
                onChange={v => setNested(['ai_reviewer', 'model'], v)}
                style={{ width: 400 }}
                placeholder="用于安全审查的模型，留空则使用主模型"
                options={modelOptions}
                allowClear
                showSearch
                disabled={!editing}
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>审查级别</label>
              <Checkbox.Group
                value={form.ai_reviewer?.review_levels ?? []}
                onChange={v => setNested(['ai_reviewer', 'review_levels'], v)}
                disabled={!editing}
                options={[
                  { label: '安全', value: 'safe' },
                  { label: '警告', value: 'caution' },
                  { label: '危险', value: 'dangerous' },
                ]}
              />
              <div><Text type="secondary" style={{ fontSize: 12 }}>选择哪些级别的命令需要 AI 审查</Text></div>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>最大命令长度</label>
              <InputNumber min={0} max={100000} value={form.ai_reviewer?.max_command_length ?? 0} onChange={v => setNested(['ai_reviewer', 'max_command_length'], v ?? 0)} style={{ maxWidth: 200 }} disabled={!editing} />
              <div><Text type="secondary" style={{ fontSize: 12 }}>超过此长度的命令会被拒绝执行</Text></div>
            </div>
          </Space>
        </Card>

        <Card title="风险级别" extra={<Text type="secondary">决定命令执行时是否需要用户确认</Text>}>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>安全命令</label>
              <TagList value={form.risk_levels?.safe ?? []} onChange={v => setNested(['risk_levels', 'safe'], v)} disabled={!editing} />
              <Text type="secondary" style={{ fontSize: 12 }}>无需确认即可执行，如 ls、cat 等只读操作</Text>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, color: '#faad14' }}>警告命令</label>
              <TagList value={form.risk_levels?.caution ?? []} onChange={v => setNested(['risk_levels', 'caution'], v)} disabled={!editing} />
              <Text type="secondary" style={{ fontSize: 12 }}>执行前会提示用户确认，如 rm、mv 等修改操作</Text>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, color: '#ff4d4f' }}>危险命令</label>
              <TagList value={form.risk_levels?.dangerous ?? []} onChange={v => setNested(['risk_levels', 'dangerous'], v)} disabled={!editing} />
              <Text type="secondary" style={{ fontSize: 12 }}>严格限制，需要多次确认，如 sudo、format 等</Text>
            </div>
          </Space>
        </Card>

        <Card title="路径沙箱" extra={<Text type="secondary">限制 Agent 可访问的目录范围</Text>}>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>写入路径</label>
              <TagList value={form.path_sandbox?.write_roots ?? []} onChange={v => setNested(['path_sandbox', 'write_roots'], v)} disabled={!editing} />
              <Text type="secondary" style={{ fontSize: 12 }}>Agent 只能在这些目录下创建或修改文件</Text>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>读取路径</label>
              <TagList value={form.path_sandbox?.read_roots ?? []} onChange={v => setNested(['path_sandbox', 'read_roots'], v)} disabled={!editing} />
              <Text type="secondary" style={{ fontSize: 12 }}>Agent 只能读取这些目录下的文件</Text>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>拒绝模式</label>
              <TagList value={form.path_sandbox?.denied_patterns ?? []} onChange={v => setNested(['path_sandbox', 'denied_patterns'], v)} disabled={!editing} />
              <Text type="secondary" style={{ fontSize: 12 }}>匹配这些模式的路径禁止访问，如 .env、*.key 等</Text>
            </div>
          </Space>
        </Card>

        {editing ? (
          <Space>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => saveAndExit(handleSave)}>
              保存
            </Button>
            <Button icon={<CloseOutlined />} onClick={cancelEdit}>
              取消
            </Button>
          </Space>
        ) : (
          <Button type="primary" icon={<EditOutlined />} onClick={startEdit}>
            编辑
          </Button>
        )}
      </Space>
    </Spin>
  )
}
