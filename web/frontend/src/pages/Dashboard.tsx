import { useEffect, useState, useRef, useCallback } from 'react'
import { Card, Row, Col, Statistic, Button, Tag, Space, Spin, Typography, Select, Tooltip, message, Switch, Alert } from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ApiOutlined,
  ThunderboltOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { useServiceStore } from '../store/serviceStore'
import { useConfigStore } from '../store/configStore'
import { getStats, getLogs } from '../api/client'

const { Text } = Typography

function formatTime(ts: string) {
  if (!ts) return ''
  return ts.replace('T', ' ').slice(0, 19)
}

function ShortId({ id }: { id: string }) {
  if (!id || id === '-') return null
  const short = id.includes('@') ? id.split('@')[0].slice(-6) : id.slice(-6)
  return <Text type="secondary" style={{ fontSize: 10, marginLeft: 4 }}>({short})</Text>
}

function DetailRow({ label, value, maxLen = 300 }: { label: string; value: string | undefined; maxLen?: number }) {
  const [expanded, setExpanded] = useState(false)
  if (!value) return null
  const needTrim = value.length > maxLen
  const display = expanded ? value : (needTrim ? value.slice(0, maxLen) + '...' : value)
  return (
    <div style={{ marginLeft: 8, marginTop: 2 }}>
      <Text type="secondary" style={{ fontSize: 11 }}>{label}: </Text>
      <Text style={{ fontSize: 11, wordBreak: 'break-all' }}>{display}</Text>
      {needTrim && (
        <Button type="link" size="small" style={{ fontSize: 10, padding: '0 2px', height: 16 }} onClick={() => setExpanded(!expanded)}>
          {expanded ? '收起' : '展开'}
        </Button>
      )}
    </div>
  )
}

function LogEntry({ entry }: { entry: any }) {
  if (typeof entry === 'string') {
    return <div style={{ padding: '4px 0' }}><Tag color="blue">日志</Tag>{entry}</div>
  }

  const ts = entry.ts || entry.timestamp || entry.time || ''
  const msg = entry.msg || ''
  const userId = entry.user_id || '-'
  const round = entry.round

  if (msg === 'agent_loop_start' || msg === 'react_start') {
    const input = entry.user_input || ''
    return (
      <div style={{ padding: '6px 8px', background: '#e6f7ff', borderRadius: 4, marginBottom: 2 }}>
        <Tag color="blue" style={{ marginRight: 6 }}>用户消息</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        {round != null && <Tag style={{ marginRight: 4, fontSize: 10 }}>R{round}</Tag>}
        <ShortId id={userId} />
        <div style={{ marginTop: 2, marginLeft: 8 }}>
          <Text strong style={{ fontSize: 12 }}>{input || '(无文本内容)'}</Text>
        </div>
        {entry.is_resuming && <Tag color="orange" style={{ marginLeft: 4, fontSize: 10 }}>恢复会话</Tag>}
        {entry.conv_len != null && <Text type="secondary" style={{ fontSize: 10, marginLeft: 4 }}>上下文{entry.conv_len}条</Text>}
      </div>
    )
  }

  if (msg === 'agent_loop_tool_detail' || msg === 'react_tool_detail') {
    const toolName = entry.tool || ''
    const toolArgs = entry.tool_args || ''
    const toolType = entry.tool_type || ''
    return (
      <div style={{ padding: '4px 8px', background: '#f0f5ff', borderRadius: 4, marginBottom: 2 }}>
        <Tag color="geekblue" style={{ marginRight: 6 }}>🔧 工具调用</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        {round != null && <Tag style={{ marginRight: 4, fontSize: 10 }}>R{round}</Tag>}
        <Text strong style={{ fontSize: 12 }}>{toolName}</Text>
        {toolType === 'skill' && <Tag color="purple" style={{ marginLeft: 4, fontSize: 10 }}>Skill</Tag>}
        <ShortId id={userId} />
        {toolArgs && <DetailRow label="参数" value={toolArgs} maxLen={200} />}
      </div>
    )
  }

  if (msg === 'agent_loop_tool_result' || msg === 'react_tool_result') {
    const toolName = entry.tool || ''
    const success = entry.success
    const preview = entry.result_preview || ''
    return (
      <div style={{ padding: '4px 8px', background: success ? '#f6ffed' : '#fff2f0', borderRadius: 4, marginBottom: 2 }}>
        <Tag color={success ? 'green' : 'red'} style={{ marginRight: 6 }}>{success ? '✅ 结果' : '❌ 失败'}</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        <Text strong style={{ fontSize: 12 }}>{toolName}</Text>
        {entry.result_len != null && <Text type="secondary" style={{ fontSize: 10, marginLeft: 4 }}>({entry.result_len}字符)</Text>}
        {preview && <DetailRow label="结果" value={preview} maxLen={200} />}
      </div>
    )
  }

  if (msg === 'agent_loop_final_response' || msg === 'react_final_response') {
    const preview = entry.text_preview || ''
    return (
      <div style={{ padding: '6px 8px', background: '#f6ffed', borderRadius: 4, marginBottom: 2, borderLeft: '3px solid #52c41a' }}>
        <Tag color="green" style={{ marginRight: 6 }}>📤 回复</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        {round != null && <Tag style={{ marginRight: 4, fontSize: 10 }}>R{round}</Tag>}
        {entry.text_len != null && <Text type="secondary" style={{ fontSize: 10 }}>({entry.text_len}字符)</Text>}
        <ShortId id={userId} />
        {preview && <DetailRow label="内容" value={preview} maxLen={300} />}
      </div>
    )
  }

  if (msg === 'agent_loop_llm_call' || msg === 'react_llm_call') {
    return (
      <div style={{ padding: '2px 8px', marginBottom: 1 }}>
        <Tag color="gold" style={{ marginRight: 6 }}>🤖 LLM</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        {round != null && <Tag style={{ fontSize: 10 }}>R{round}</Tag>}
        {entry.conv_len != null && <Text type="secondary" style={{ fontSize: 10, marginLeft: 4 }}>上下文{entry.conv_len}条</Text>}
      </div>
    )
  }

  if (msg === 'agent_loop_tool_calls' || msg === 'react_tool_calls') {
    const tools: string[] = entry.tools || []
    return (
      <div style={{ padding: '2px 8px', marginBottom: 1 }}>
        <Tag color="geekblue" style={{ marginRight: 6 }}>🔧 工具</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        {round != null && <Tag style={{ marginRight: 4, fontSize: 10 }}>R{round}</Tag>}
        {tools.map(t => <Tag key={t} style={{ fontSize: 10, marginRight: 2 }}>{t}</Tag>)}
      </div>
    )
  }

  if (msg === 'agent_loop_done' || msg === 'react_done') {
    return (
      <div style={{ padding: '4px 8px', marginBottom: 2 }}>
        <Tag color="green" style={{ marginRight: 6 }}>✔️ 完成</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        {entry.response_len != null && <Text type="secondary" style={{ fontSize: 10 }}>({entry.response_len}字符)</Text>}
      </div>
    )
  }

  if (msg === 'new_invocation') {
    return (
      <div style={{ padding: '4px 8px', background: '#e6f7ff', borderRadius: 4, marginBottom: 2 }}>
        <Tag color="blue" style={{ marginRight: 6 }}>🆕 新会话</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        {entry.user_input && <Text style={{ fontSize: 12 }}>{entry.user_input.slice(0, 80)}</Text>}
        <ShortId id={userId} />
      </div>
    )
  }

  if (msg === 'interrupt_resume') {
    return (
      <div style={{ padding: '4px 8px', background: '#fff7e6', borderRadius: 4, marginBottom: 2 }}>
        <Tag color="orange" style={{ marginRight: 6 }}>🔄 恢复</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        {entry.user_input && <Text style={{ fontSize: 12 }}>{entry.user_input.slice(0, 80)}</Text>}
      </div>
    )
  }

  if (msg === 'send_response') {
    return (
      <div style={{ padding: '4px 8px', marginBottom: 2 }}>
        <Tag color="cyan" style={{ marginRight: 6 }}>💬 已发送</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        {entry.text_preview && <Text style={{ fontSize: 11 }}>{entry.text_preview.slice(0, 100)}</Text>}
        {entry.text_len != null && <Text type="secondary" style={{ fontSize: 10, marginLeft: 4 }}>({entry.text_len}字符)</Text>}
      </div>
    )
  }

  if (msg === 'send_confirm') {
    return (
      <div style={{ padding: '4px 8px', marginBottom: 2 }}>
        <Tag color="orange" style={{ marginRight: 6 }}>⚠️ 确认</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        {entry.confirm_type && <Tag style={{ fontSize: 10 }}>{entry.confirm_type}</Tag>}
        {entry.text_preview && <Text style={{ fontSize: 11, marginLeft: 4 }}>{entry.text_preview.slice(0, 100)}</Text>}
      </div>
    )
  }

  if (msg === 'classify_result') {
    return (
      <div style={{ padding: '2px 8px', marginBottom: 1 }}>
        <Tag color="default" style={{ marginRight: 6 }}>📨 分类</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        {entry.msg_type && <Tag style={{ fontSize: 10 }}>{entry.msg_type}</Tag>}
      </div>
    )
  }

  if (msg === 'react_needs_confirm') {
    return (
      <div style={{ padding: '4px 8px', background: '#fff7e6', borderRadius: 4, marginBottom: 2 }}>
        <Tag color="orange" style={{ marginRight: 6 }}>⚠️ 待确认</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        <Text strong style={{ fontSize: 12 }}>{entry.tool || ''}</Text>
        {entry.tool_args && <DetailRow label="参数" value={entry.tool_args} maxLen={200} />}
      </div>
    )
  }

  if (msg === 'agent_loop_max_rounds' || msg === 'react_max_rounds_reached') {
    return (
      <div style={{ padding: '4px 8px', background: '#fff2f0', borderRadius: 4, marginBottom: 2 }}>
        <Tag color="red" style={{ marginRight: 6 }}>⚠️ 达到上限</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        <Text style={{ fontSize: 12 }}>已达到最大轮次 ({entry.rounds || '?'})</Text>
      </div>
    )
  }

  if (msg === 'qrcode_generated' || msg === 'qrcode_scanned' || msg === 'login_confirmed' || msg === 'qrcode_expired') {
    const map: Record<string, { label: string; color: string; icon: string }> = {
      qrcode_generated: { label: '登录', color: 'cyan', icon: '📱' },
      qrcode_scanned: { label: '登录', color: 'cyan', icon: '📱' },
      login_confirmed: { label: '登录', color: 'green', icon: '✅' },
      qrcode_expired: { label: '登录', color: 'orange', icon: '⚠️' },
    }
    const info = map[msg] || { label: '登录', color: 'blue', icon: '📋' }
    const text = entry.msg || entry.message || ''
    return (
      <div style={{ padding: '4px 8px', marginBottom: 2 }}>
        <Tag color={info.color} style={{ marginRight: 6 }}>{info.icon} {info.label}</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        <Text style={{ fontSize: 12 }}>{text}</Text>
      </div>
    )
  }

  if (msg === 'dangerous_command_confirmed' || msg === 'cloud_consent_confirmed' || msg === 'pip_install_confirmed' || msg === 'skill_action_confirmed') {
    return (
      <div style={{ padding: '4px 8px', background: '#f6ffed', borderRadius: 4, marginBottom: 2 }}>
        <Tag color="green" style={{ marginRight: 6 }}>✅ 确认</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        <Text style={{ fontSize: 12 }}>{msg.replace(/_/g, ' ')}</Text>
        {entry.command && <DetailRow label="命令" value={entry.command} maxLen={200} />}
        {entry.package && <DetailRow label="包" value={entry.package} />}
        {entry.skill && <DetailRow label="技能" value={entry.skill} />}
      </div>
    )
  }

  const level = entry.level || ''
  if (level === 'ERROR' || level === 'error') {
    return (
      <div style={{ padding: '4px 8px', background: '#fff2f0', borderRadius: 4, marginBottom: 2 }}>
        <Tag color="red" style={{ marginRight: 6 }}>错误</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        <Text type="danger" style={{ fontSize: 12 }}>{typeof msg === 'string' ? msg : JSON.stringify(msg)}</Text>
      </div>
    )
  }
  if (level === 'WARNING' || level === 'warning') {
    return (
      <div style={{ padding: '4px 8px', background: '#fffbe6', borderRadius: 4, marginBottom: 2 }}>
        <Tag color="orange" style={{ marginRight: 6 }}>警告</Tag>
        <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
        <Text style={{ fontSize: 12 }}>{typeof msg === 'string' ? msg : JSON.stringify(msg)}</Text>
      </div>
    )
  }

  return (
    <div style={{ padding: '2px 8px', marginBottom: 1 }}>
      <Tag color="default" style={{ marginRight: 6 }}>日志</Tag>
      <span style={{ color: '#999', fontSize: 11, marginRight: 6 }}>{formatTime(ts)}</span>
      <Text style={{ fontSize: 12 }}>{typeof msg === 'string' ? msg : JSON.stringify(msg)}</Text>
    </div>
  )
}

export default function Dashboard() {
  const { status, loading, fetchStatus, start, stop, restart } = useServiceStore()
  const { config, fetchConfig, updateConfig } = useConfigStore()
  const [stats, setStats] = useState<any>(null)
  const [logs, setLogs] = useState<any[]>([])
  const [logTotal, setLogTotal] = useState<number>(0)
  const [showAll, setShowAll] = useState(false)
  const [uptimeOffset, setUptimeOffset] = useState<number>(0)
  const logTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const uptimeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchLogs = useCallback(async () => {
    try {
      const data = await getLogs({ lines: 200, key_only: !showAll })
      if (data && Array.isArray(data.entries)) {
        setLogs(data.entries)
        setLogTotal(data.total || data.entries.length)
      }
    } catch (e) {
      console.error('Failed to fetch logs:', e)
    }
  }, [showAll])

  useEffect(() => {
    fetchStatus()
    fetchConfig('llm')
    getStats().then(setStats).catch(() => {})
    fetchLogs()
  }, [])

  useEffect(() => {
    if (status?.running) {
      fetchLogs()
      logTimerRef.current = setInterval(fetchLogs, 3000)
    } else {
      if (logTimerRef.current) {
        clearInterval(logTimerRef.current)
        logTimerRef.current = null
      }
    }
    return () => {
      if (logTimerRef.current) {
        clearInterval(logTimerRef.current)
      }
    }
  }, [status?.running, fetchLogs])

  useEffect(() => {
    if (status?.running && status?.uptime != null) {
      setUptimeOffset(0)
      uptimeTimerRef.current = setInterval(() => {
        setUptimeOffset(prev => prev + 1)
      }, 1000)
    } else {
      setUptimeOffset(0)
      if (uptimeTimerRef.current) {
        clearInterval(uptimeTimerRef.current)
        uptimeTimerRef.current = null
      }
    }
    return () => {
      if (uptimeTimerRef.current) {
        clearInterval(uptimeTimerRef.current)
      }
    }
  }, [status?.running, status?.uptime])

  const handleAction = async (action: () => Promise<void>) => {
    await action()
    await fetchStatus()
    setTimeout(fetchLogs, 1000)
  }

  const handleBackendChange = async (value: string) => {
    try {
      await updateConfig('llm', { ...config, agent_backend: value })
      message.success(`运行模式已切换为: ${value === 'legacy' ? '受限模式' : '完整模式'}`)
      await fetchConfig('llm')
    } catch {
      message.error('切换失败')
    }
  }

  const formatUptime = (seconds: number | null) => {
    if (!seconds && seconds !== 0) return '-'
    const totalSec = Math.floor(seconds)
    const h = Math.floor(totalSec / 3600)
    const m = Math.floor((totalSec % 3600) / 60)
    const s = totalSec % 60
    if (h > 0) return `${h}时${m}分${s}秒`
    if (m > 0) return `${m}分${s}秒`
    return `${s}秒`
  }

  const currentUptime = status?.uptime != null ? status.uptime + uptimeOffset : null

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="仪表盘显示服务运行状态和统计信息。启动服务会根据当前配置（.env 和 config.yaml）运行 Agent。"
        />

        <Card title="服务状态">
          <Row gutter={[16, 16]} align="middle">
            <Col span={6}>
              <Statistic
                title="运行状态"
                value={status?.running ? '运行中' : '已停止'}
                prefix={status?.running ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
                valueStyle={{ color: status?.running ? '#52c41a' : '#ff4d4f', fontSize: 20 }}
              />
            </Col>
            <Col span={6}>
              <Statistic title="进程 PID" value={status?.pid ?? '-'} />
            </Col>
            <Col span={6}>
              <Statistic title="运行时间" value={formatUptime(currentUptime)} />
            </Col>
            <Col span={6}>
              <div style={{ marginBottom: 4 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>运行模式</Text>
              </div>
              <Tooltip title={status?.running ? '运行中无法切换模式，请先停止服务' : ''}>
                <Select
                  value={config?.agent_backend || 'legacy'}
                  onChange={handleBackendChange}
                  style={{ width: 140 }}
                  disabled={status?.running}
                  options={[
                    { value: 'legacy', label: '🔒 受限模式' },
                    { value: 'langgraph', label: '🚀 完整模式' },
                  ]}
                />
              </Tooltip>
            </Col>
          </Row>
          <div style={{ marginTop: 16 }}>
            <Space>
              <Tooltip title="启动 Agent 服务，使用当前配置运行">
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={() => handleAction(start)}
                  disabled={status?.running}
                >
                  启动
                </Button>
              </Tooltip>
              <Tooltip title="停止正在运行的 Agent 服务">
                <Button
                  danger
                  icon={<PauseCircleOutlined />}
                  onClick={() => handleAction(stop)}
                  disabled={!status?.running}
                >
                  停止
                </Button>
              </Tooltip>
              <Tooltip title="重启 Agent 服务（先停止再启动）">
                <Button
                  icon={<ReloadOutlined />}
                  onClick={() => handleAction(restart)}
                  disabled={!status?.running}
                >
                  重启
                </Button>
              </Tooltip>
            </Space>
          </div>
        </Card>

        <Row gutter={16}>
          <Col span={8}>
            <Card>
              <Statistic
                title="LLM 调用次数"
                value={stats?.llm_calls ?? 0}
                prefix={<ApiOutlined />}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic
                title="Token 用量"
                value={stats?.total_tokens ?? 0}
                prefix={<ThunderboltOutlined />}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic
                title="估算费用"
                value={`$${(stats?.estimated_usd ?? 0).toFixed(4)}`}
                prefix={<TeamOutlined />}
              />
            </Card>
          </Col>
        </Row>

        <Card
          title={<span>运行日志 {logTotal > 0 && <Tag color="blue" style={{ marginLeft: 8 }}>共 {logTotal} 条</Tag>}</span>}
          extra={
            <Space>
              <Text type="secondary" style={{ fontSize: 11 }}>全部日志</Text>
              <Switch size="small" checked={showAll} onChange={setShowAll} />
              {!status?.running && <Tag color="orange">服务未运行</Tag>}
              <Tooltip title="手动刷新日志列表">
                <Button size="small" icon={<ReloadOutlined />} onClick={fetchLogs}>
                  刷新
                </Button>
              </Tooltip>
            </Space>
          }
        >
          <div style={{ maxHeight: 500, overflow: 'auto', fontFamily: 'monospace', fontSize: 12 }}>
            {logs.length === 0 ? (
              <div style={{ color: '#999', textAlign: 'center', padding: 20 }}>
                {!status?.running ? (
                  <>
                    <div>服务未运行，点击上方"启动"按钮启动 Agent</div>
                    <div style={{ marginTop: 8, fontSize: 11 }}>日志文件: workspace/data/debug/agent.jsonl</div>
                  </>
                ) : (
                  <>
                    <div>暂无日志记录</div>
                    <div style={{ marginTop: 8, fontSize: 11 }}>等待 Agent 产生日志...</div>
                  </>
                )}
              </div>
            ) : (
              logs.map((entry, i) => <LogEntry key={i} entry={entry} />)
            )}
          </div>
        </Card>
      </Space>
    </Spin>
  )
}
