import { useEffect } from 'react'
import { Input, Collapse, Button, Space, message, Spin, Alert, Tooltip } from 'antd'
import { SaveOutlined, EditOutlined, CloseOutlined } from '@ant-design/icons'
import { useConfigStore } from '../store/configStore'
import { useEditMode } from '../hooks/useEditMode'

const promptFields = [
  { key: 'system_prompt', label: '系统提示词' },
  { key: 'classify_prompt', label: '分类提示词' },
  { key: 'vision_prompt', label: '视觉提示词' },
  { key: 'preference_extract_prompt', label: '偏好提取提示词' },
  { key: 'ai_safety_prompt', label: 'AI 安全提示词' },
]

export default function Prompts() {
  const { config, loading, saving, fetchConfig, updateConfig } = useConfigStore()
  const { editing, startEdit, cancelEdit, saveAndExit } = useEditMode()

  useEffect(() => {
    fetchConfig('prompts')
  }, [])

  const handleSave = async () => {
    try {
      await updateConfig('prompts', config)
      message.success('保存成功')
    } catch {
      message.error('保存失败')
    }
  }

  const handleChange = (key: string, value: string) => {
    const newConfig = { ...config, [key]: value }
    useConfigStore.setState({ config: newConfig })
  }

  const collapseItems = promptFields.map(({ key, label }) => ({
    key,
    label,
    children: (
      <Input.TextArea
        rows={10}
        value={config?.[key] ?? ''}
        onChange={e => handleChange(key, e.target.value)}
        placeholder={`请输入${label}`}
        style={{ fontFamily: 'monospace' }}
        disabled={!editing}
      />
    ),
  }))

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="提示词控制 Agent 的行为方式和回复风格。修改后需重启服务生效。"
        />

        <Collapse items={collapseItems} />
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
