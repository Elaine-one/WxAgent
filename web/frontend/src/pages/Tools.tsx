import { useEffect, useState } from 'react'
import { Input, InputNumber, Select, Collapse, Button, Space, message, Spin, Alert } from 'antd'
import { SaveOutlined, EditOutlined, CloseOutlined } from '@ant-design/icons'
import { useConfigStore } from '../store/configStore'
import { useEditMode } from '../hooks/useEditMode'
import TagList from '../components/TagList'

export default function Tools() {
  const { config, loading, saving, fetchConfig, updateConfig } = useConfigStore()
  const [form, setForm] = useState<Record<string, any>>({})
  const { editing, startEdit, cancelEdit, saveAndExit } = useEditMode()

  useEffect(() => {
    fetchConfig('tools')
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
      await updateConfig('tools', form)
      message.success('保存成功')
    } catch {
      message.error('保存失败')
    }
  }

  const collapseItems = [
    {
      key: 'aria2',
      label: 'Aria2 下载',
      children: (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>RPC URL</label>
            <Input disabled={!editing} value={form.aria2?.rpc_url ?? ''} onChange={e => setNested(['aria2', 'rpc_url'], e.target.value)} placeholder="请输入 Aria2 RPC URL" style={{ maxWidth: 400 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>RPC 请求超时(秒)</label>
            <InputNumber disabled={!editing} min={1} max={60} value={form.aria2?.rpc_timeout ?? 5} onChange={v => setNested(['aria2', 'rpc_timeout'], v ?? 5)} style={{ maxWidth: 200 }} />
          </div>
        </Space>
      ),
    },
    {
      key: 'whisper',
      label: 'Whisper 语音识别',
      children: (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>模型</label>
            <Select disabled={!editing} value={form.whisper?.model ?? 'base'} onChange={v => setNested(['whisper', 'model'], v)} style={{ width: 200 }} options={[
              { value: 'tiny', label: 'Tiny' },
              { value: 'base', label: 'Base' },
              { value: 'small', label: 'Small' },
              { value: 'medium', label: 'Medium' },
              { value: 'large', label: 'Large' },
            ]} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>设备</label>
            <Select disabled={!editing} value={form.whisper?.device ?? 'cpu'} onChange={v => setNested(['whisper', 'device'], v)} style={{ width: 200 }} options={[
              { value: 'cpu', label: 'CPU' },
              { value: 'cuda', label: 'CUDA' },
            ]} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>计算类型</label>
            <Select disabled={!editing} value={form.whisper?.compute_type ?? 'int8'} onChange={v => setNested(['whisper', 'compute_type'], v)} style={{ width: 200 }} options={[
              { value: 'int8', label: 'Int8' },
              { value: 'float16', label: 'Float16' },
              { value: 'float32', label: 'Float32' },
            ]} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>云端模型</label>
            <Input disabled={!editing} value={form.whisper?.cloud_model ?? ''} onChange={e => setNested(['whisper', 'cloud_model'], e.target.value)} placeholder="请输入云端模型名称" style={{ maxWidth: 400 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>SILK 解码超时(秒)</label>
            <InputNumber disabled={!editing} min={5} max={300} value={form.whisper?.silk_decode_timeout ?? 30} onChange={v => setNested(['whisper', 'silk_decode_timeout'], v ?? 30)} style={{ maxWidth: 200 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>FFmpeg 音频提取超时(秒)</label>
            <InputNumber disabled={!editing} min={10} max={3600} value={form.whisper?.ffmpeg_audio_extract_timeout ?? 300} onChange={v => setNested(['whisper', 'ffmpeg_audio_extract_timeout'], v ?? 300)} style={{ maxWidth: 200 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>FFmpeg 采样率(Hz)</label>
            <InputNumber disabled={!editing} min={8000} max={48000} step={1000} value={form.whisper?.ffmpeg_sample_rate ?? 24000} onChange={v => setNested(['whisper', 'ffmpeg_sample_rate'], v ?? 24000)} style={{ maxWidth: 200 }} />
          </div>
        </Space>
      ),
    },
    {
      key: 'ocr',
      label: 'OCR 文字识别',
      children: (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>语言</label>
            <Select disabled={!editing} value={form.ocr?.lang ?? 'ch'} onChange={v => setNested(['ocr', 'lang'], v)} style={{ width: 200 }} options={[
              { value: 'ch', label: '中文' },
              { value: 'eng', label: '英文' },
              { value: 'japan', label: '日文' },
              { value: 'korean', label: '韩文' },
            ]} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>备用模型</label>
            <Input disabled={!editing} value={form.ocr?.fallback_model ?? ''} onChange={e => setNested(['ocr', 'fallback_model'], e.target.value)} placeholder="请输入备用 OCR 模型" style={{ maxWidth: 400 }} />
          </div>
        </Space>
      ),
    },
    {
      key: 'web',
      label: 'Web 搜索与抓取',
      children: (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>最大搜索结果数</label>
            <InputNumber disabled={!editing} min={1} max={50} value={form.web?.search_max_results ?? 5} onChange={v => setNested(['web', 'search_max_results'], v ?? 5)} style={{ maxWidth: 200 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>网页抓取最大字符数</label>
            <InputNumber disabled={!editing} min={0} max={1000000} value={form.web?.fetch_max_chars ?? 8000} onChange={v => setNested(['web', 'fetch_max_chars'], v ?? 8000)} style={{ maxWidth: 200 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>网页抓取超时(秒)</label>
            <InputNumber disabled={!editing} min={1} max={120} value={form.web?.fetch_timeout ?? 15} onChange={v => setNested(['web', 'fetch_timeout'], v ?? 15)} style={{ maxWidth: 200 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>GitHub 镜像</label>
            <TagList disabled={!editing} value={form.web?.github_mirrors ?? []} onChange={v => setNested(['web', 'github_mirrors'], v)} inputWidth={200} />
          </div>
        </Space>
      ),
    },
    {
      key: 'download',
      label: '下载工具',
      children: (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>HTTP 下载超时(秒)</label>
            <InputNumber disabled={!editing} min={1} max={3600} value={form.download?.http_download_timeout ?? 180} onChange={v => setNested(['download', 'http_download_timeout'], v ?? 180)} style={{ maxWidth: 200 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>视频下载超时(秒)</label>
            <InputNumber disabled={!editing} min={1} max={7200} value={form.download?.video_download_timeout ?? 3600} onChange={v => setNested(['download', 'video_download_timeout'], v ?? 3600)} style={{ maxWidth: 200 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>文件大小限制(MB)</label>
            <InputNumber disabled={!editing} min={1} max={1024} value={form.download?.file_size_limit_mb ?? 50} onChange={v => setNested(['download', 'file_size_limit_mb'], v ?? 50)} style={{ maxWidth: 200 }} addonAfter="MB" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>CDN 下载超时(秒)</label>
            <InputNumber disabled={!editing} min={1} max={300} value={form.download?.cdn_download_timeout ?? 60} onChange={v => setNested(['download', 'cdn_download_timeout'], v ?? 60)} style={{ maxWidth: 200 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>图片下载超时(秒)</label>
            <InputNumber disabled={!editing} min={1} max={120} value={form.download?.image_download_timeout ?? 15} onChange={v => setNested(['download', 'image_download_timeout'], v ?? 15)} style={{ maxWidth: 200 }} />
          </div>
        </Space>
      ),
    },
    {
      key: 'file',
      label: '文件工具',
      children: (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>文件大小限制(MB)</label>
            <InputNumber disabled={!editing} min={1} max={1024} value={form.file?.file_size_limit_mb ?? 50} onChange={v => setNested(['file', 'file_size_limit_mb'], v ?? 50)} style={{ maxWidth: 200 }} addonAfter="MB" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>文件读取最大字符数</label>
            <InputNumber disabled={!editing} min={1000} max={10000000} step={10000} value={form.file?.file_read_max_chars ?? 100000} onChange={v => setNested(['file', 'file_read_max_chars'], v ?? 100000)} style={{ maxWidth: 250 }} />
          </div>
        </Space>
      ),
    },
    {
      key: 'code',
      label: '代码工具',
      children: (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>Pip 安装超时(秒)</label>
            <InputNumber disabled={!editing} min={10} max={600} value={form.code?.pip_install_timeout ?? 120} onChange={v => setNested(['code', 'pip_install_timeout'], v ?? 120)} style={{ maxWidth: 200 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>代码输出总大小限制(字节)</label>
            <InputNumber disabled={!editing} min={10000} max={1000000} step={10000} value={form.code?.total_output_limit ?? 100000} onChange={v => setNested(['code', 'total_output_limit'], v ?? 100000)} style={{ maxWidth: 250 }} />
          </div>
        </Space>
      ),
    },
    {
      key: 'tasks',
      label: '任务配置',
      children: (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>IO 线程池大小</label>
            <InputNumber disabled={!editing} min={1} max={64} value={form.tasks?.io_pool_max_workers ?? 8} onChange={v => setNested(['tasks', 'io_pool_max_workers'], v ?? 8)} style={{ maxWidth: 200 }} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>CPU 线程池大小</label>
            <InputNumber disabled={!editing} min={1} max={64} value={form.tasks?.cpu_pool_max_workers ?? 2} onChange={v => setNested(['tasks', 'cpu_pool_max_workers'], v ?? 2)} style={{ maxWidth: 200 }} />
          </div>
        </Space>
      ),
    },
  ]

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert type="info" showIcon message="工具配置控制各工具模块的运行参数。修改后需重启服务生效。" />
        <Collapse items={collapseItems} defaultActiveKey={['aria2', 'web']} />
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
