import { useEffect, useState } from 'react'
import { Table, Input, Select, Button, Space, Card, message, Spin, Alert, Typography, Tooltip } from 'antd'
import { PlusOutlined, DeleteOutlined, SaveOutlined, EditOutlined, CloseOutlined } from '@ant-design/icons'
import { useConfigStore } from '../store/configStore'
import { useEditMode } from '../hooks/useEditMode'

const { Text } = Typography

interface ActionRow {
  key: string
  name: string
  command: string
  risk: string
  description: string
  shell: string
}

interface WhitelistEntry {
  key: string
  name: string
  command: string
}

export default function SystemControl() {
  const { config, loading, saving, fetchConfig, updateConfig } = useConfigStore()
  const [actions, setActions] = useState<ActionRow[]>([])
  const [whitelist, setWhitelist] = useState<WhitelistEntry[]>([])
  const { editing, startEdit, cancelEdit, saveAndExit } = useEditMode()

  useEffect(() => {
    fetchConfig('system_control')
  }, [])

  useEffect(() => {
    if (config && Object.keys(config).length > 0 && !editing) {
      const actionsDict = config.actions ?? {}
      const actionsList = Object.entries(actionsDict).map(([name, a]: [string, any], i: number) => ({
        key: String(i),
        name,
        command: a.command ?? '',
        risk: a.risk ?? 'safe',
        description: a.description ?? '',
        shell: a.shell ?? 'cmd',
      }))
      setActions(actionsList)

      const whitelistDict = config.app_whitelist ?? {}
      const whitelistList = Object.entries(whitelistDict).map(([name, command], i) => ({
        key: String(i),
        name,
        command: command as string,
      }))
      setWhitelist(whitelistList)
    }
  }, [config, editing])

  const handleSave = async () => {
    try {
      const actionsDict: Record<string, any> = {}
      actions.forEach(({ name, command, risk, description, shell }) => {
        if (name) {
          actionsDict[name] = { command, risk, description, shell }
        }
      })

      const appWhitelist: Record<string, string> = {}
      whitelist.forEach(({ name, command }) => {
        if (name) appWhitelist[name] = command
      })

      await updateConfig('system_control', {
        actions: actionsDict,
        app_whitelist: appWhitelist,
      })
      message.success('保存成功')
    } catch {
      message.error('保存失败')
    }
  }

  const addAction = () => setActions([...actions, { key: Date.now().toString(), name: '', command: '', risk: 'safe', description: '', shell: 'cmd' }])
  const addWhitelist = () => setWhitelist([...whitelist, { key: Date.now().toString(), name: '', command: '' }])

  const actionColumns = [
    { title: '名称', dataIndex: 'name', width: 120, render: (_: string, __: any, i: number) => <Input value={actions[i].name} onChange={e => { const n = [...actions]; n[i] = { ...n[i], name: e.target.value }; setActions(n) }} disabled={!editing} /> },
    { title: '命令', dataIndex: 'command', render: (_: string, __: any, i: number) => <Input value={actions[i].command} onChange={e => { const n = [...actions]; n[i] = { ...n[i], command: e.target.value }; setActions(n) }} disabled={!editing} /> },
    { title: '风险级别', dataIndex: 'risk', width: 100, render: (_: string, __: any, i: number) => (
      <Select value={actions[i].risk} onChange={v => { const n = [...actions]; n[i] = { ...n[i], risk: v }; setActions(n) }} style={{ width: '100%' }} disabled={!editing} options={[
        { value: 'safe', label: '安全' },
        { value: 'caution', label: '警告' },
        { value: 'dangerous', label: '危险' },
      ]} />
    )},
    { title: '描述', dataIndex: 'description', render: (_: string, __: any, i: number) => <Input value={actions[i].description} onChange={e => { const n = [...actions]; n[i] = { ...n[i], description: e.target.value }; setActions(n) }} disabled={!editing} /> },
    { title: 'Shell', dataIndex: 'shell', width: 80, render: (_: string, __: any, i: number) => <Select value={actions[i].shell} onChange={v => { const n = [...actions]; n[i] = { ...n[i], shell: v }; setActions(n) }} style={{ width: '100%' }} disabled={!editing} options={[{ value: 'cmd', label: 'cmd' }, { value: 'powershell', label: 'ps' }]} /> },
    { title: '操作', width: 60, render: (_: any, __: any, i: number) => <Button type="text" danger icon={<DeleteOutlined />} onClick={() => setActions(actions.filter((_, j) => j !== i))} disabled={!editing} /> },
  ]

  const whitelistColumns = [
    { title: '应用名称', dataIndex: 'name', width: 150, render: (_: string, __: any, i: number) => <Input value={whitelist[i].name} onChange={e => { const n = [...whitelist]; n[i] = { ...n[i], name: e.target.value }; setWhitelist(n) }} disabled={!editing} /> },
    { title: '命令', dataIndex: 'command', render: (_: string, __: any, i: number) => <Input value={whitelist[i].command} onChange={e => { const n = [...whitelist]; n[i] = { ...n[i], command: e.target.value }; setWhitelist(n) }} disabled={!editing} /> },
    { title: '操作', width: 60, render: (_: any, __: any, i: number) => <Button type="text" danger icon={<DeleteOutlined />} onClick={() => setWhitelist(whitelist.filter((_, j) => j !== i))} disabled={!editing} /> },
  ]

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="系统控制定义可执行的系统命令和应用白名单。风险级别决定命令执行时的安全策略。"
        />

        <Card title="系统动作" extra={<Text type="secondary">预设的命令模板，Agent 可按名称调用</Text>}>
          <div style={{ marginBottom: 8 }}>
            <Button type="dashed" icon={<PlusOutlined />} onClick={addAction} disabled={!editing}>添加动作</Button>
          </div>
          <Table columns={actionColumns} dataSource={actions} pagination={false} size="small" />
        </Card>

        <Card 
          title="应用白名单" 
          extra={<Text type="secondary">允许 Agent 打开的应用程序</Text>}
        >
          <Alert
            type="info"
            showIcon
            message="配置示例"
            description={
              <div style={{ fontSize: 12 }}>
                <div style={{ marginBottom: 8 }}>
                  <Text strong>常用命令格式：</Text>
                </div>
                <div style={{ marginLeft: 12, marginBottom: 4 }}>
                  • <Text code>start chrome</Text> — 启动 Chrome 浏览器（系统 PATH 中的应用）
                </div>
                <div style={{ marginLeft: 12, marginBottom: 4 }}>
                  • <Text code>start msedge</Text> — 启动 Edge 浏览器
                </div>
                <div style={{ marginLeft: 12, marginBottom: 4 }}>
                  • <Text code>code</Text> — 启动 VS Code（命令行工具）
                </div>
                <div style={{ marginLeft: 12, marginBottom: 4 }}>
                  • <Text code>start https://www.bilibili.com</Text> — 打开网页
                </div>
                <div style={{ marginLeft: 12, marginBottom: 4 }}>
                  • <Text code>start "" "C:\Path\To\App.exe"</Text> — 完整路径启动应用
                </div>
                <div style={{ marginLeft: 12, marginTop: 8 }}>
                  <Text type="secondary">提示：应用名称是调用时的标识，命令是实际执行的启动命令</Text>
                </div>
              </div>
            }
            style={{ marginBottom: 16 }}
          />
          <div style={{ marginBottom: 8 }}>
            <Button type="dashed" icon={<PlusOutlined />} onClick={addWhitelist} disabled={!editing}>添加白名单</Button>
          </div>
          <Table columns={whitelistColumns} dataSource={whitelist} pagination={false} size="small" />
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
