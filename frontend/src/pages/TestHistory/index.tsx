/**
 * 页面 5：测试历史
 */
import React, { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, Select, DatePicker, Modal, Descriptions, message,
} from 'antd'
import {
  ReloadOutlined,
  EyeOutlined,
  ReloadOutlined as RedoOutlined,
} from '@ant-design/icons'
import { testApi } from '../../api/client'
import { TestRun } from '../../types'
import dayjs from 'dayjs'

const { RangePicker } = DatePicker

export default function TestHistory() {
  const [tests, setTests] = useState<TestRun[]>([])
  const [loading, setLoading] = useState(false)
  const [detailVisible, setDetailVisible] = useState(false)
  const [selectedTest, setSelectedTest] = useState<TestRun | null>(null)
  const [filters, setFilters] = useState<{
    record_id?: string
    asr_model_id?: number
    date_range?: [dayjs.Dayjs, dayjs.Dayjs] | null
  }>({})

  const fetchTests = async () => {
    setLoading(true)
    try {
      const params: any = { limit: 100 }
      if (filters.record_id) params.record_id = filters.record_id
      const data = await testApi.getHistory(params)
      setTests(data as TestRun[])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTests()
  }, [filters.record_id])

  const showDetail = (test: TestRun) => {
    setSelectedTest(test)
    setDetailVisible(true)
  }

  const columns = [
    {
      title: '测试时间',
      dataIndex: 'created_at',
      key: 'time',
      width: 180,
      render: (t: string) => new Date(t).toLocaleString('zh-CN'),
      sorter: (a: TestRun, b: TestRun) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    },
    { title: '病历号', dataIndex: 'record_id', key: 'record_id', width: 120 },
    { title: '日期', dataIndex: 'date', key: 'date', width: 100 },
    { title: 'ASR 模型 ID', dataIndex: 'asr_model_id', key: 'asr', width: 100 },
    { title: 'LLM 模型 ID', dataIndex: 'llm_model_id', key: 'llm', width: 100,
      render: (id: number | null) => id ?? '-'
    },
    {
      title: '准确率',
      dataIndex: 'accuracy',
      key: 'accuracy',
      width: 100,
      render: (a: number | null) => a !== null ? (
        <Tag color={a >= 0.8 ? 'green' : a >= 0.5 ? 'orange' : 'red'}>
          {(a * 100).toFixed(0)}%
        </Tag>
      ) : '-',
    },
    {
      title: '耗时',
      dataIndex: 'duration_seconds',
      key: 'duration',
      width: 80,
      render: (d: number) => `${d.toFixed(1)}s`,
    },
    {
      title: '人工修正',
      dataIndex: 'human_corrected',
      key: 'corrected',
      width: 80,
      render: (c: boolean) => c ? <Tag color="blue">是</Tag> : <Tag>否</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: any, record: TestRun) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => showDetail(record)}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div className="page-header">
        <h2>测试历史</h2>
      </div>

      <Card
        title="历史记录"
        extra={
          <Space>
            <Select
              placeholder="按病历号筛选"
              allowClear
              showSearch
              style={{ width: 160 }}
              onChange={(v) => setFilters((f) => ({ ...f, record_id: v }))}
              options={Array.from(new Set(tests.map((t) => t.record_id))).map((id) => ({ value: id, label: id }))}
            />
            <Button icon={<ReloadOutlined />} onClick={fetchTests}>刷新</Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={tests}
          pagination={{ pageSize: 20, showSizeChanger: true }}
          size="middle"
        />
      </Card>

      <Modal
        title={`测试详情 - ${selectedTest?.record_id}`}
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={null}
        width={700}
      >
        {selectedTest && (
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="测试时间">
              {new Date(selectedTest.created_at).toLocaleString('zh-CN')}
            </Descriptions.Item>
            <Descriptions.Item label="病历号">{selectedTest.record_id}</Descriptions.Item>
            <Descriptions.Item label="ASR 模型 ID">{selectedTest.asr_model_id}</Descriptions.Item>
            <Descriptions.Item label="LLM 模型 ID">{selectedTest.llm_model_id ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="准确率">
              {selectedTest.accuracy !== null ? `${(selectedTest.accuracy * 100).toFixed(1)}%` : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="耗时">{selectedTest.duration_seconds}s</Descriptions.Item>
          </Descriptions>
        )}

        {selectedTest?.full_transcript && (
          <div style={{ marginTop: 16 }}>
            <h4>完整转写：</h4>
            <div style={{ padding: 12, background: '#f5f5f5', borderRadius: 4, maxHeight: 200, overflow: 'auto', fontSize: 13 }}>
              {selectedTest.full_transcript}
            </div>
          </div>
        )}

        {selectedTest?.summary_text && (
          <div style={{ marginTop: 16 }}>
            <h4>总结：</h4>
            <div style={{ padding: 12, background: '#f6ffed', borderRadius: 4 }}>
              {selectedTest.summary_text}
            </div>
          </div>
        )}

        {selectedTest?.structured_result && (
          <div style={{ marginTop: 16 }}>
            <h4>结构化结果：</h4>
            <pre style={{ padding: 12, background: '#f5f5f5', borderRadius: 4, fontSize: 12 }}>
              {JSON.stringify(selectedTest.structured_result, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  )
}
