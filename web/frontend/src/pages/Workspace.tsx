import { useEffect, useState } from 'react'
import { Input, Button, Card, Space, message, Spin, Alert } from 'antd'
import { SaveOutlined, EditOutlined, CloseOutlined } from '@ant-design/icons'
import { useConfigStore } from '../store/configStore'
import { useEditMode } from '../hooks/useEditMode'
import TagList from '../components/TagList'

export default function Workspace() {
  const { config, loading, saving, fetchConfig, updateConfig } = useConfigStore()
  const [form, setForm] = useState<Record<string, any>>({})
  const { editing, startEdit, cancelEdit, saveAndExit } = useEditMode()

  useEffect(() => {
    fetchConfig('workspace')
  }, [])

  useEffect(() => {
    if (config && Object.keys(config).length > 0 && !editing) {
      setForm(config)
    }
  }, [config, editing])

  const set = (key: string, value: any) => setForm(prev => ({ ...prev, [key]: value }))

  const handleSave = async () => {
    try {
      await updateConfig('workspace', form)
      message.success('保存成功')
    } catch {
      message.error('保存失败')
    }
  }

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert type="info" showIcon message="工作区是 Agent 存储文件和执行操作的基础目录。子目录会在启动时自动创建。" />
        <Card title="工作区配置">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>工作区目录</label>
              <Input value={form.workspace_dir ?? ''} onChange={e => set('workspace_dir', e.target.value)} placeholder="请输入工作区目录路径" style={{ maxWidth: 500 }} disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>子目录</label>
              <TagList value={form.subdirs ?? []} onChange={v => set('subdirs', v)} disabled={!editing} />
            </div>
          </Space>
        </Card>

        <Card title="虚拟环境包">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>基础包</label>
              <TagList value={form.venv_packages?.basic ?? []} onChange={v => setForm(prev => ({ ...prev, venv_packages: { ...(prev.venv_packages ?? {}), basic: v } }))} disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>完整包</label>
              <TagList value={form.venv_packages?.full ?? []} onChange={v => setForm(prev => ({ ...prev, venv_packages: { ...(prev.venv_packages ?? {}), full: v } }))} disabled={!editing} />
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
            编辑配置
          </Button>
        )}
      </Space>
    </Spin>
  )
}
