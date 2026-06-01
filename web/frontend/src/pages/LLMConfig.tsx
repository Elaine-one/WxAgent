import { useEffect } from 'react'
import { Form, Input, Select, InputNumber, Button, Collapse, Space, message, Spin, Alert, Row, Col, Tooltip } from 'antd'
import { ApiOutlined, SaveOutlined, EditOutlined, CloseOutlined } from '@ant-design/icons'
import { useConfigStore } from '../store/configStore'
import { testLLM, testLLMCurrent } from '../api/client'
import { useEditMode } from '../hooks/useEditMode'

const providerOptions = [
  { value: 'openai', label: 'OpenAI 兼容' },
  { value: 'anthropic', label: 'Anthropic' },
]

export default function LLMConfig() {
  const { config, loading, saving, fetchConfig, updateConfig } = useConfigStore()
  const [form] = Form.useForm()
  const { editing, startEdit, cancelEdit, saveAndExit } = useEditMode()

  useEffect(() => {
    fetchConfig('llm')
  }, [])

  useEffect(() => {
    if (config && Object.keys(config).length > 0 && !editing) {
      form.setFieldsValue(config)
    }
  }, [config, editing])

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      await updateConfig('llm', values)
      message.success('保存成功')
    } catch {
      message.error('保存失败')
    }
  }

  const handleTest = async () => {
    try {
      message.loading({ content: '正在测试连接...', key: 'test-llm', duration: 0 })

      let result
      if (editing) {
        const values = await form.validateFields(['provider', 'api_key', 'base_url', 'model'])
        result = await testLLM(values)
      } else {
        result = await testLLMCurrent()
      }

      message.destroy('test-llm')
      if (result.success) {
        message.success(`连接测试成功 (延迟: ${result.latency_ms?.toFixed(0)}ms)`)
      } else {
        message.error(`连接测试失败: ${result.message || '未知错误'}`)
      }
    } catch (e: any) {
      message.destroy('test-llm')
      const detail = e?.response?.data?.detail || e?.message || '连接测试失败'
      message.error(detail)
    }
  }

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="所有配置存储在 .env 文件中，API Key 会被自动脱敏显示。修改后需重启服务生效。"
        />

        <Form form={form} layout="vertical" disabled={!editing}>
          <Collapse defaultActiveKey={['main', 'vision', 'fallback']} items={[{
            key: 'main',
            label: '主模型配置（文本对话）',
            children: (
              <>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item label="LLM 提供商" name="provider">
                      <Select options={providerOptions} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="模型名称" name="model">
                      <Input placeholder="如 deepseek-chat、gpt-4o" />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item label="API Key" name="api_key">
                      <Input.Password placeholder="请输入 API Key" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="最大 Token 数" name="max_tokens">
                      <InputNumber min={1} max={1000000} style={{ width: '100%' }} placeholder="请输入最大 Token 数" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="Base URL" name="base_url">
                  <Input placeholder="请输入 Base URL" />
                </Form.Item>
              </>
            ),
          }, {
            key: 'vision',
            label: '视觉模型配置（图片识别）',
            children: (
              <>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item label="视觉 API Key" name="vision_api_key">
                      <Input.Password placeholder="留空则使用主 API Key" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="视觉模型名称" name="vision_model">
                      <Input placeholder="如 gpt-4o、glm-4v、claude-sonnet-4-6" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="视觉 Base URL" name="vision_base_url">
                  <Input placeholder="留空则使用主 Base URL" />
                </Form.Item>
              </>
            ),
          }, {
            key: 'fallback',
            label: '备用模型（当主模型不可用时自动切换）',
            children: (
              <>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item label="备用 API Key" name="fallback_api_key">
                      <Input.Password placeholder="留空则使用主 API Key" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="备用模型名称" name="fallback_model">
                      <Input placeholder="请输入备用模型名称" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="备用 Base URL" name="fallback_base_url">
                  <Input placeholder="留空则使用主 Base URL" />
                </Form.Item>
              </>
            ),
          }]} />
        </Form>

        <div style={{ display: 'flex', gap: 8 }}>
          {editing ? (
            <>
              <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => saveAndExit(handleSave)}>
                保存配置
              </Button>
              <Button icon={<CloseOutlined />} onClick={cancelEdit}>
                取消
              </Button>
              <Tooltip title="使用当前表单中的配置测试连接（脱敏的 API Key 会自动使用真实值）">
                <Button icon={<ApiOutlined />} onClick={handleTest}>
                  测试连接
                </Button>
              </Tooltip>
            </>
          ) : (
            <>
              <Button type="primary" icon={<EditOutlined />} onClick={startEdit}>
                编辑配置
              </Button>
              <Tooltip title="使用当前 .env 中保存的配置测试 LLM API 连接">
                <Button icon={<ApiOutlined />} onClick={handleTest}>
                  测试连接
                </Button>
              </Tooltip>
            </>
          )}
        </div>
      </Space>
    </Spin>
  )
}
