import { useEffect, useState } from 'react'
import { InputNumber, Button, Card, Space, message, Spin, Alert, Tooltip } from 'antd'
import { SaveOutlined, EditOutlined, CloseOutlined } from '@ant-design/icons'
import { useConfigStore } from '../store/configStore'
import { useEditMode } from '../hooks/useEditMode'

interface LimitField {
  key: string
  label: string
  description: string
  min?: number
  max?: number
}

const basicLimits: LimitField[] = [
  { key: 'max_llm_calls_per_task', label: '每任务最大 LLM 调用次数', description: '单个任务中允许的最大 LLM 调用次数' },
  { key: 'max_history', label: '最大历史记录', description: '保留的最大对话历史条数' },
  { key: 'max_retries_per_step', label: '每步最大重试次数', description: '单个步骤的最大重试次数' },
  { key: 'python_timeout_seconds', label: 'Python 超时(秒)', description: 'Python 执行超时时间', min: 1 },
  { key: 'python_max_output_bytes', label: 'Python 最大输出字节', description: 'Python 执行最大输出字节数', min: 0 },
  { key: 'shell_timeout_seconds', label: 'Shell 超时(秒)', description: 'Shell 命令执行超时时间', min: 1 },
]

const advancedLimits: LimitField[] = [
  { key: 'max_tokens', label: '最大 Token 数', description: '单次请求最大 Token 数', min: 1 },
  { key: 'max_chars', label: '最大字符数', description: '单次响应最大字符数', min: 1 },
  { key: 'debounce_delay', label: '防抖延迟(秒)', description: '消息发送防抖延迟', min: 0 },
  { key: 'max_sessions', label: '最大会话数', description: '同时允许的最大会话数', min: 1 },
  { key: 'session_ttl_seconds', label: '会话 TTL(秒)', description: '会话存活时间', min: 0 },
  { key: 'messages_window', label: '消息窗口大小', description: '上下文消息窗口大小', min: 1 },
  { key: 'short_term_max_messages', label: '短期最大消息数', description: '短期记忆最大消息数', min: 1 },
  { key: 'long_term_max_messages', label: '长期最大消息数', description: '长期记忆最大消息数', min: 1 },
  { key: 'llm_fallback_timeout', label: 'LLM 回退超时(秒)', description: 'LLM 请求回退超时时间', min: 0 },
  { key: 'bubble_send_interval', label: '气泡发送间隔(秒)', description: '消息气泡发送间隔', min: 0 },
]

export default function Limits() {
  const { config, loading, saving, fetchConfig, updateConfig } = useConfigStore()
  const [form, setForm] = useState<Record<string, any>>({})
  const { editing, startEdit, cancelEdit, saveAndExit } = useEditMode()

  useEffect(() => {
    fetchConfig('limits')
  }, [])

  useEffect(() => {
    if (config && Object.keys(config).length > 0 && !editing) {
      setForm(config)
    }
  }, [config, editing])

  const set = (key: string, value: any) => setForm(prev => ({ ...prev, [key]: value }))

  const handleSave = async () => {
    try {
      await updateConfig('limits', form)
      message.success('保存成功')
    } catch {
      message.error('保存失败')
    }
  }

  const renderField = (field: LimitField) => (
    <div key={field.key} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '8px 0' }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 500 }}>{field.label}</div>
        <div style={{ fontSize: 12, color: '#999' }}>{field.description}</div>
      </div>
      <InputNumber
        min={field.min}
        max={field.max}
        value={form[field.key] ?? 0}
        onChange={v => set(field.key, v ?? 0)}
        style={{ width: 160 }}
        disabled={!editing}
      />
    </div>
  )

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="行为限制控制 Agent 的资源使用和调用频率，防止过度消耗。"
        />

        <Card title="基础限制">
          {basicLimits.map(renderField)}
        </Card>

        <Card title="高级限制">
          {advancedLimits.map(renderField)}
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
          <Tooltip title="进入编辑模式">
            <Button type="primary" icon={<EditOutlined />} onClick={startEdit}>
              编辑配置
            </Button>
          </Tooltip>
        )}
      </Space>
    </Spin>
  )
}
