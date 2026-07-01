/**
 * 页面 2：模型配置
 */
import React, { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, Modal, Form, Input, Select, Switch, message, Popconfirm, Tooltip,
} from 'antd'
import {
  PlusOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { modelApi } from '../../api/client'
import { ModelConfig } from '../../types'

const { Option } = Select

export default function ModelConfigPage() {
  const [models, setModels] = useState<ModelConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ModelConfig | null>(null)
  const [testing, setTesting] = useState<Record<number, boolean>>({})
  const [form] = Form.useForm()

  const fetchModels = async () => {
    setLoading(true)
    try {
      const [asr, llm] = await Promise.all([
        modelApi.list('asr'),
        modelApi.list('llm'),
      ])
      setModels([...(asr as ModelConfig[]), ...(llm as ModelConfig[])])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchModels()
    // 初始化默认模型
    modelApi.initDefaults().catch(() => {})
  }, [])

  const handleTest = async (id: number) => {
    setTesting((t) => ({ ...t, [id]: true }))
    try {
      const res: any = await modelApi.test(id)
      if (res.success) {
        message.success(`连通 (${res.latency_ms}ms)`)
      } else {
        message.error(`不通: ${res.message}`)
      }
    } finally {
      setTesting((t) => ({ ...t, [id]: false }))
    }
  }

  const handleSave = async (values: any) => {
    try {
      if (editing) {
        await modelApi.update(editing.id, values)
        message.success('更新成功')
      } else {
        await modelApi.create(values)
        message.success('创建成功')
      }
      setModalOpen(false)
      setEditing(null)
      form.resetFields()
      await fetchModels()
    } catch {
      // 错误已在拦截器处理
    }
  }

  const handleDelete = async (id: number) => {
    await modelApi.delete(id)
    message.success('删除成功')
    await fetchModels()
  }

  const openEdit = (record: ModelConfig) => {
    setEditing(record)
    form.setFieldsValue(record)
    setModalOpen(true)
  }

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ model_type: 'asr', provider: 'local', status: 'active' })
    setModalOpen(true)
  }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '类型',
      dataIndex: 'model_type',
      key: 'model_type',
      width: 80,
      render: (t: string) => (
        <Tag color={t === 'asr' ? 'blue' : 'purple'}>{t.toUpperCase()}</Tag>
      ),
    },
    {
      title: 'Provider',
      dataIndex: 'provider',
      key: 'provider',
      width: 100,
      render: (p: string) => <Tag>{p}</Tag>,
    },
    {
      title: 'Endpoint',
      dataIndex: 'endpoint',
      key: 'endpoint',
      ellipsis: true,
      render: (url: string) => (
        <Tooltip title={url}>
          <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{url}</span>
        </Tooltip>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (s: string, r: ModelConfig) => (
        <Tag color={s === 'active' ? 'green' : 'default'}>
          {s === 'active' ? '启用' : '停用'}
        </Tag>
      ),
    },
    {
      title: '默认',
      dataIndex: 'is_default',
      key: 'is_default',
      width: 60,
      render: (d: boolean) => d ? <Tag color="gold">默认</Tag> : null,
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: any, record: ModelConfig) => (
        <Space>
          <Button
            size="small"
            icon={<ApiOutlined />}
            loading={testing[record.id]}
            onClick={() => handleTest(record.id)}
          >
            测试
          </Button>
          <Button size="small" onClick={() => openEdit(record)}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div className="page-header">
        <h2>模型配置</h2>
      </div>

      <Card
        title="已配置模型"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchModels}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新增模型
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={models}
          pagination={false}
          size="middle"
        />
      </Card>

      <Modal
        title={editing ? '编辑模型' : '新增模型'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditing(null); }}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="如：本地 FunASR" />
          </Form.Item>
          <Form.Item name="model_type" label="类型" rules={[{ required: true }]}>
            <Select>
              <Option value="asr">ASR（语音转文字）</Option>
              <Option value="llm">LLM（语义理解）</Option>
            </Select>
          </Form.Item>
          <Form.Item name="provider" label="Provider" rules={[{ required: true }]}>
            <Select>
              <Option value="local">本地</Option>
              <Option value="iflytek">讯飞</Option>
              <Option value="tencent">腾讯</Option>
            </Select>
          </Form.Item>
          <Form.Item name="endpoint" label="Endpoint URL" rules={[{ required: true }]}>
            <Input placeholder="http://172.16.10.142:50000/transcribe" />
          </Form.Item>
          <Form.Item name="model_name" label="模型名称（可选）">
            <Input placeholder="如：spark-v3.5" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key">
            <Input.Password placeholder="留空则不设置" />
          </Form.Item>
          <Form.Item name="api_secret" label="API Secret（可选）">
            <Input.Password />
          </Form.Item>
          <Form.Item name="is_default" label="设为默认" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select>
              <Option value="active">启用</Option>
              <Option value="inactive">停用</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
