import { useEffect, useState } from 'react'
import { Switch, Input, InputNumber, Slider, Checkbox, Button, Card, Space, message, Spin, Tooltip, Alert } from 'antd'
import { SaveOutlined, EditOutlined, CloseOutlined } from '@ant-design/icons'
import { useConfigStore } from '../store/configStore'
import { useEditMode } from '../hooks/useEditMode'
import TagList from '../components/TagList'

export default function Memory() {
  const { config, loading, saving, fetchConfig, updateConfig } = useConfigStore()
  const { editing, startEdit, cancelEdit, saveAndExit } = useEditMode()
  const [form, setForm] = useState<Record<string, any>>({})

  useEffect(() => {
    fetchConfig('memory')
  }, [])

  useEffect(() => {
    if (config && Object.keys(config).length > 0 && !editing) {
      setForm(config)
    }
  }, [config, editing])

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
      await updateConfig('memory', form)
      message.success('保存成功')
    } catch {
      message.error('保存失败')
    }
  }

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert type="info" showIcon message="记忆检索配置控制 Agent 的长期记忆能力。索引器负责文件索引，检索器负责语义搜索。" />
        <Card title="索引器配置">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>启用索引器</span>
              <Tooltip title="开启后自动索引工作区文件，支持语义搜索">
                <Switch checked={form.indexer?.enabled ?? false} onChange={v => setNested(['indexer', 'enabled'], v)} disabled={!editing} />
              </Tooltip>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>监控目录</label>
              <TagList value={form.indexer?.watch_dirs ?? []} onChange={v => setNested(['indexer', 'watch_dirs'], v)} disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>支持的文件类型</label>
              <TagList value={form.indexer?.supported_types ?? []} onChange={v => setNested(['indexer', 'supported_types'], v)} disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>空闲 CPU 阈值</label>
              <InputNumber min={0} max={100} value={form.indexer?.idle_cpu_threshold ?? 0} onChange={v => setNested(['indexer', 'idle_cpu_threshold'], v ?? 0)} style={{ maxWidth: 200 }} addonAfter="%" disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>扫描间隔(秒)</label>
              <InputNumber min={1} value={form.indexer?.scan_interval_seconds ?? 60} onChange={v => setNested(['indexer', 'scan_interval_seconds'], v ?? 60)} style={{ maxWidth: 200 }} disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>最大文档字符数</label>
              <InputNumber min={0} value={form.indexer?.max_document_chars ?? 0} onChange={v => setNested(['indexer', 'max_document_chars'], v ?? 0)} style={{ maxWidth: 200 }} disabled={!editing} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>使用 Watchdog</span>
              <Tooltip title="使用 Watchdog 库实时监控文件变化，而非定时扫描">
                <Switch checked={form.indexer?.use_watchdog ?? false} onChange={v => setNested(['indexer', 'use_watchdog'], v)} disabled={!editing} />
              </Tooltip>
            </div>
          </Space>
        </Card>

        <Card title="检索器配置">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>向量权重</label>
              <Slider min={0} max={1} step={0.1} value={form.retriever?.vector_weight ?? 0.5} onChange={v => setNested(['retriever', 'vector_weight'], v)} disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>关键词权重</label>
              <Slider min={0} max={1} step={0.1} value={form.retriever?.keyword_weight ?? 0.5} onChange={v => setNested(['retriever', 'keyword_weight'], v)} disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>时间衰减权重</label>
              <Slider min={0} max={1} step={0.1} value={form.retriever?.time_decay_weight ?? 0} onChange={v => setNested(['retriever', 'time_decay_weight'], v)} disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>时间衰减半衰期(天)</label>
              <InputNumber min={0} value={form.retriever?.time_decay_half_life_days ?? 30} onChange={v => setNested(['retriever', 'time_decay_half_life_days'], v ?? 30)} style={{ maxWidth: 200 }} disabled={!editing} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>默认范围</span>
              <Checkbox checked={form.retriever?.default_scope ?? false} onChange={e => setNested(['retriever', 'default_scope'], e.target.checked)} disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>默认 Top K</label>
              <InputNumber min={1} max={100} value={form.retriever?.default_top_k ?? 5} onChange={v => setNested(['retriever', 'default_top_k'], v ?? 5)} style={{ maxWidth: 200 }} disabled={!editing} />
            </div>
          </Space>
        </Card>

        <Card title="嵌入模型">
          <Input value={form.embedding_model ?? ''} onChange={e => setForm(prev => ({ ...prev, embedding_model: e.target.value }))} placeholder="请输入嵌入模型名称" style={{ maxWidth: 400 }} disabled={!editing} />
        </Card>

        <Card title="记忆检索参数">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>检索数量 (Top K)</label>
              <InputNumber min={1} max={50} value={form.search_top_k ?? 3} onChange={v => setForm(prev => ({ ...prev, search_top_k: v ?? 3 }))} style={{ maxWidth: 200 }} disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>相关性阈值</label>
              <Slider min={0} max={1} step={0.05} value={form.relevance_threshold ?? 0.5} onChange={v => setForm(prev => ({ ...prev, relevance_threshold: v }))} disabled={!editing} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4 }}>偏好提取置信度阈值</label>
              <Slider min={0} max={1} step={0.05} value={form.preference_confidence_threshold ?? 0.6} onChange={v => setForm(prev => ({ ...prev, preference_confidence_threshold: v }))} disabled={!editing} />
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
