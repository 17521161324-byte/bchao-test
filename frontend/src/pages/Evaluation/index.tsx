/**
 * 页面 4：结果评估
 */
import React, { useEffect, useState } from 'react'
import {
  Card, Table, Tag, Button, Space, Descriptions, Input, Form, message, Spin, Empty, Row, Col, Statistic,
} from 'antd'
import {
  CheckCircleFilled,
  CloseCircleFilled,
  EditOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import { testApi } from '../../api/client'
import { TestRun } from '../../types'

const { TextArea } = Input

export default function Evaluation() {
  const [tests, setTests] = useState<TestRun[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedTest, setSelectedTest] = useState<TestRun | null>(null)
  const [editing, setEditing] = useState(false)
  const [form] = Form.useForm()

  const fetchTests = async () => {
    setLoading(true)
    try {
      const data = await testApi.getHistory({ limit: 50 })
      setTests(data as TestRun[])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTests()
  }, [])

  const handleSelectTest = (test: TestRun) => {
    setSelectedTest(test)
    setEditing(false)
    if (test.structured_result) {
      form.setFieldsValue({ structured_result: JSON.stringify(test.structured_result, null, 2) })
    }
  }

  const handleSaveCorrection = async () => {
    if (!selectedTest) return
    try {
      const values = await form.validateFields()
      const structured = JSON.parse(values.structured_result)
      await testApi.updateEval(selectedTest.id, {
        structured_result: structured,
        human_corrected: true,
      })
      message.success('评估已保存')
      setEditing(false)
      await fetchTests()
    } catch (e: any) {
      if (e.errorFields) {
        message.error('JSON 格式有误')
      }
    }
  }

  const renderEvaluationTable = (evaluation: any) => {
    if (!evaluation || !evaluation.fields) return null

    const fieldLabels: Record<string, string> = {
      right_follicle_total: '右侧卵泡总数',
      left_follicle_total: '左侧卵泡总数',
      endometrium_thickness: '内膜厚度',
      endometrium_type: '内膜类型',
      right_ovary_length: '右卵巢长',
      right_ovary_width: '右卵巢宽',
      left_ovary_length: '左卵巢长',
      left_ovary_width: '左卵巢宽',
    }

    const rows = Object.entries(evaluation.fields).map(([key, val]: [string, any]) => ({
      field: fieldLabels[fieldLabels[key] || key],
      identified: val.identified ?? '-',
      truth: val.truth ?? '-',
      diff: val.diff !== null && val.diff !== undefined ? String(val.diff) : '-',
      match: val.match,
      key,
    }))

    const columns = [
      { title: '字段', dataIndex: 'field', key: 'field' },
      { title: '识别值', dataIndex: 'identified', key: 'identified' },
      { title: '真实值', dataIndex: 'truth', key: 'truth' },
      { title: '差异', dataIndex: 'diff', key: 'diff' },
      {
        title: '结果',
        dataIndex: 'match',
        key: 'match',
        render: (match: boolean) =>
          match ? (
            <Tag icon={<CheckCircleFilled />} color="success">正确</Tag>
          ) : (
            <Tag icon={<CloseCircleFilled />} color="error">错误</Tag>
          ),
      },
    ]

    return <Table columns={columns} dataSource={rows} pagination={false} size="small" rowClassName={(r) => r.match ? '' : 'diff-wrong'} />
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h2>结果评估</h2>
      </div>

      <Row gutter={16}>
        <Col span={14}>
          <Card title="测试记录" extra={<Button onClick={fetchTests}>刷新</Button>}>
            <Table
              rowKey="id"
              loading={loading}
              size="small"
              pagination={{ pageSize: 10 }}
              dataSource={tests}
              onRow={(record) => ({ onClick: () => handleSelectTest(record), style: { cursor: 'pointer' } })}
              rowClassName={(r) => r.id === selectedTest?.id ? 'ant-table-row-selected' : ''}
              columns={[
                { title: '时间', dataIndex: 'created_at', key: 'time', width: 160,
                  render: (t: string) => new Date(t).toLocaleString('zh-CN') },
                { title: '病历号', dataIndex: 'record_id', key: 'record_id' },
                { title: 'ASR 模型', dataIndex: 'asr_model_id', key: 'asr', width: 100 },
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
                  title: '人工修正',
                  dataIndex: 'human_corrected',
                  key: 'corrected',
                  width: 80,
                  render: (c: boolean) => c ? <Tag color="blue">已修正</Tag> : <Tag>未修正</Tag>,
                },
              ]}
            />
          </Card>
        </Col>

        <Col span={10}>
          {selectedTest ? (
            <Card
              title={`评估详情 - ${selectedTest.record_id}`}
              extra={
                editing ? (
                  <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveCorrection}>
                    保存
                  </Button>
                ) : (
                  <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>
                    修正
                  </Button>
                )
              }
            >
              {selectedTest.evaluation ? (
                <>
                  <Row gutter={8} style={{ marginBottom: 16 }}>
                    <Col span={8}>
                      <Statistic title="总字段" value={selectedTest.evaluation.total_fields} />
                    </Col>
                    <Col span={8}>
                      <Statistic title="正确" value={selectedTest.evaluation.correct_fields} valueStyle={{ color: '#52c41a' }} />
                    </Col>
                    <Col span={8}>
                      <Statistic
                        title="准确率"
                        value={((selectedTest.evaluation.accuracy || 0) * 100).toFixed(1)}
                        suffix="%"
                      />
                    </Col>
                  </Row>
                  {renderEvaluationTable(selectedTest.evaluation)}
                </>
              ) : (
                <Empty description="无评估数据（可能缺少 ground truth）" />
              )}

              {editing && (
                <Form form={form} style={{ marginTop: 16 }}>
                  <Form.Item name="structured_result" rules={[{ required: true }]}>
                    <TextArea rows={10} style={{ fontFamily: 'monospace', fontSize: 12 }} />
                  </Form.Item>
                </Form>
              )}
            </Card>
          ) : (
            <Card>
              <Empty description="请选择一条测试记录" />
            </Card>
          )}
        </Col>
      </Row>
    </div>
  )
}
