/**
 * 页面 3：单条测试（核心功能）
 */
import React, { useEffect, useState, useCallback } from 'react'
import {
  Card, Row, Col, Select, Button, Space, Tag, Progress, Typography, message, Spin, Empty, Descriptions,
} from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  LoadingOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons'
import { useAppStore } from '../../store'
import { testApi, startTestSSE } from '../../api/client'
import { ModelConfig, TestProgressEvent } from '../../types'
import AudioPlayer from '../../components/AudioPlayer'
import SegList from '../../components/SegList'

const { Text, Title } = Typography

export default function SingleTest() {
  const { audioTree, asrModels, llmModels, fetchAudioTree, fetchModels } = useAppStore()

  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [selectedRecord, setSelectedRecord] = useState<string | null>(null)
  const [selectedPatient, setSelectedPatient] = useState<any>(null)
  const [asrModelId, setAsrModelId] = useState<number | undefined>()
  const [llmModelId, setLlmModelId] = useState<number | undefined>()

  const [testing, setTesting] = useState(false)
  const [progress, setProgress] = useState<TestProgressEvent | null>(null)
  const [testResult, setTestResult] = useState<any>(null)

  useEffect(() => {
    fetchAudioTree()
    fetchModels()
  }, [])

  useEffect(() => {
    // 设置默认 ASR
    const defaultAsr = asrModels.find((m) => m.is_default) || asrModels[0]
    if (defaultAsr) setAsrModelId(defaultAsr.id)
  }, [asrModels])

  // 获取当前选中日期下的病历号列表
  const currentPatients = (() => {
    const folder = audioTree.find((f) => f.date === selectedDate)
    return folder?.patients || []
  })()

  const handleDateChange = (date: string) => {
    setSelectedDate(date)
    setSelectedRecord(null)
    setSelectedPatient(null)
    setTestResult(null)
  }

  const handleRecordChange = (recordId: string) => {
    setSelectedRecord(recordId)
    const folder = audioTree.find((f) => f.date === selectedDate)
    const patient = folder?.patients.find((p) => p.record_id === recordId)
    setSelectedPatient(patient)
    setTestResult(null)
  }

  const handleStartTest = useCallback(() => {
    if (!selectedRecord || !asrModelId) {
      message.warning('请选择病历号和 ASR 模型')
      return
    }

    setTesting(true)
    setTestResult(null)
    setProgress({ stage: 'asr', message: '准备开始...' })

    const es = startTestSSE({
      record_id: selectedRecord,
      asr_model_id: asrModelId,
      llm_model_id: llmModelId,
      prompt_version: 'v1.0',
    })

    es.addEventListener('progress', (e: MessageEvent) => {
      const data: TestProgressEvent = JSON.parse(e.data)
      setProgress(data)
    })

    es.addEventListener('complete', async (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      es.close()
      setTesting(false)
      // 获取完整结果
      try {
        const result = await testApi.getResult(data.test_id)
        setTestResult(result)
        message.success('测试完成')
      } catch {
        message.error('获取结果失败')
      }
    })

    es.addEventListener('error', (e: any) => {
      es.close()
      setTesting(false)
      message.error('测试执行出错')
    })

    es.onerror = () => {
      es.close()
      setTesting(false)
    }
  }, [selectedRecord, asrModelId, llmModelId])

  const getProgressPercent = () => {
    if (!progress) return 0
    if (progress.stage === 'asr' && progress.total) {
      return Math.round(((progress.current || 0) / progress.total) * 100)
    }
    if (progress.stage === 'llm') return 95
    if (progress.stage === 'complete') return 100
    return 0
  }

  const renderResult = () => {
    if (!testResult) return null

    return (
      <Card title="测试结果" style={{ marginTop: 16 }}>
        <Descriptions column={2} size="small" bordered>
          <Descriptions.Item label="耗时">{testResult.duration_seconds}s</Descriptions.Item>
          <Descriptions.Item label="ASR 段数">{testResult.asr_results?.length ?? 0}</Descriptions.Item>
        </Descriptions>

        {testResult.summary_text && (
          <div style={{ marginTop: 16 }}>
            <Text strong>总结：</Text>
            <div style={{ marginTop: 8, padding: 12, background: '#f6ffed', borderRadius: 4 }}>
              {testResult.summary_text}
            </div>
          </div>
        )}

        {testResult.structured_result && (
          <div style={{ marginTop: 16 }}>
            <Text strong>结构化结果：</Text>
            <pre style={{ marginTop: 8, padding: 12, background: '#f5f5f5', borderRadius: 4, fontSize: 12 }}>
              {JSON.stringify(testResult.structured_result, null, 2)}
            </pre>
          </div>
        )}

        {testResult.accuracy !== null && testResult.accuracy !== undefined && (
          <div style={{ marginTop: 16 }}>
            <Tag color={testResult.accuracy >= 0.8 ? 'green' : testResult.accuracy >= 0.5 ? 'orange' : 'red'}>
              准确率: {(testResult.accuracy * 100).toFixed(1)}%
            </Tag>
          </div>
        )}

        {testResult.llm_raw_output && (
          <details style={{ marginTop: 16 }}>
            <summary style={{ cursor: 'pointer', color: '#666' }}>查看 LLM 原始输出</summary>
            <pre style={{ marginTop: 8, padding: 12, background: '#f5f5f5', borderRadius: 4, fontSize: 12, maxHeight: 300, overflow: 'auto' }}>
              {testResult.llm_raw_output}
            </pre>
          </details>
        )}
      </Card>
    )
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h2>单条测试</h2>
      </div>

      <Row gutter={16}>
        <Col span={10}>
          <Card title="测试配置">
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <div>
                <Text type="secondary">选择日期：</Text>
                <Select
                  style={{ width: '100%', marginTop: 4 }}
                  placeholder="选择日期"
                  value={selectedDate}
                  onChange={handleDateChange}
                  options={audioTree.map((f) => ({ value: f.date, label: f.date }))}
                />
              </div>

              <div>
                <Text type="secondary">选择病历号：</Text>
                <Select
                  style={{ width: '100%', marginTop: 4 }}
                  placeholder="选择病历号"
                  value={selectedRecord}
                  onChange={handleRecordChange}
                  disabled={!selectedDate}
                  showSearch
                  optionFilterProp="label"
                  options={currentPatients.map((p) => ({
                    value: p.record_id,
                    label: `${p.record_id} (${p.segs.length} 段)`,
                    disabled: !p.has_result,
                  }))}
                />
              </div>

              <div>
                <Text type="secondary">ASR 模型：</Text>
                <Select
                  style={{ width: '100%', marginTop: 4 }}
                  placeholder="选择 ASR 模型"
                  value={asrModelId}
                  onChange={setAsrModelId}
                  options={asrModels.map((m) => ({ value: m.id, label: m.name }))}
                />
              </div>

              <div>
                <Text type="secondary">LLM 模型（可选）：</Text>
                <Select
                  style={{ width: '100%', marginTop: 4 }}
                  placeholder="选择 LLM 模型"
                  value={llmModelId}
                  onChange={setLlmModelId}
                  allowClear
                  options={llmModels.map((m) => ({ value: m.id, label: m.name }))}
                />
              </div>

              <Button
                type="primary"
                size="large"
                block
                icon={testing ? <LoadingOutlined /> : <PlayCircleOutlined />}
                onClick={handleStartTest}
                disabled={testing || !selectedRecord || !asrModelId}
              >
                {testing ? '测试中...' : '开始测试'}
              </Button>

              {testing && (
                <div>
                  <Progress percent={getProgressPercent()} status="active" />
                  <div style={{ marginTop: 4, color: '#666', fontSize: 12 }}>
                    {progress?.message || '正在执行...'}
                    {progress?.current && progress?.total && (
                      <span> ({progress.current}/{progress.total})</span>
                    )}
                  </div>
                </div>
              )}
            </Space>
          </Card>
        </Col>

        <Col span={14}>
          {selectedPatient ? (
            <>
              <Card title={`录音播放 - ${selectedPatient.record_id}`}>
                <AudioPlayer
                  segs={selectedPatient.segs}
                  highlightSegIndex={
                    testing && progress?.stage === 'asr' && progress.current
                      ? progress.current - 1
                      : undefined
                  }
                />
              </Card>

              <Card title="分段转写" style={{ marginTop: 16 }}>
                <SegList
                  segs={selectedPatient.segs}
                  asrResults={testResult?.asr_results || []}
                />
              </Card>

              {renderResult()}
            </>
          ) : (
            <Card>
              <Empty description="请先选择日期和病历号" />
            </Card>
          )}
        </Col>
      </Row>
    </div>
  )
}
