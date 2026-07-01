/**
 * Seg 列表组件 - 显示每个 seg 的转写结果
 */
import React from 'react'
import { List, Tag, Typography } from 'antd'
import { CheckCircleFilled, LoadingOutlined, WarningOutlined } from '@ant-design/icons'
import { ASRSegResult, AudioSeg } from '../../types'

const { Text } = Typography

interface SegListProps {
  segs: AudioSeg[]
  asrResults: ASRSegResult[]
  currentSegIndex?: number
  onSegClick?: (index: number) => void
}

export default function SegList({ segs, asrResults, currentSegIndex, onSegClick }: SegListProps) {
  const resultMap = new Map(asrResults.map((r) => [r.seg_index, r]))

  return (
    <List
      size="small"
      dataSource={segs}
      renderItem={(seg, idx) => {
        const result = resultMap.get(seg.seg_index)
        const hasResult = !!result
        const isCurrent = idx === currentSegIndex

        let statusIcon = <WarningOutlined style={{ color: '#ccc' }} />
        let statusTag = <Tag>未转写</Tag>
        if (hasResult) {
          statusIcon = <CheckCircleFilled style={{ color: '#52c41a' }} />
          statusTag = <Tag color="success">已完成</Tag>
        } else if (idx === currentSegIndex) {
          statusIcon = <LoadingOutlined style={{ color: '#1677ff' }} />
          statusTag = <Tag color="processing">转写中</Tag>
        }

        return (
          <List.Item
            key={seg.id}
            style={{
              cursor: 'pointer',
              background: isCurrent ? '#e6f4ff' : 'transparent',
              padding: '8px 12px',
              borderRadius: 4,
            }}
            onClick={() => onSegClick?.(idx)}
          >
            <List.Item.Meta
              avatar={statusIcon}
              title={
                <span style={{ fontSize: 13 }}>
                  <Text strong>第 {seg.seg_index} 段</Text>
                  <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>
                    {seg.filename}
                  </Text>
                  {statusTag}
                </span>
              }
              description={
                hasResult ? (
                  <Text style={{ fontSize: 12 }}>{result!.text || '(空)'}</Text>
                ) : (
                  <Text type="secondary" style={{ fontSize: 12 }}>等待转写...</Text>
                )
              }
            />
          </List.Item>
        )
      }}
    />
  )
}
