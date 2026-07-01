/**
 * 页面 1：数据导入与管理
 */
import React, { useEffect, useState } from 'react'
import {
  Card, Row, Col, Tree, Upload, Button, Statistic, Tag, Space, message, Spin, Empty,
} from 'antd'
import {
  FolderOutlined,
  CustomerServiceOutlined,
  CloudUploadOutlined,
  ReloadOutlined,
  ScanOutlined,
} from '@ant-design/icons'
import type { DataNode } from 'antd/es/tree'
import { audioApi, resultApi } from '../../api/client'
import { useAppStore } from '../../store'

export default function DataImport() {
  const {
    audioTree, dataStatus, loadingTree,
    fetchAudioTree, fetchDataStatus, scanRecordings,
  } = useAppStore()
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    fetchAudioTree()
    fetchDataStatus()
  }, [])

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      const res: any = await resultApi.upload(file)
      message.success(`导入成功，共 ${res.imported} 条`)
      await fetchAudioTree()
      await fetchDataStatus()
    } catch {
      // 错误已在 axios 拦截器处理
    } finally {
      setUploading(false)
    }
    return false // 阻止默认上传行为
  }

  const handleScan = async () => {
    message.info('正在扫描录音目录...')
    await scanRecordings()
    message.success('扫描完成')
  }

  // 构建树形数据
  const buildTreeData = (): DataNode[] => {
    return audioTree.map((folder) => ({
      title: (
        <Space>
          <FolderOutlined />
          <span>{folder.date}</span>
          <Tag color="blue">{folder.patient_count} 例</Tag>
        </Space>
      ),
      key: `date-${folder.id}`,
      children: folder.patients.map((patient) => ({
        title: (
          <Space>
            <CustomerServiceOutlined />
            <span>{patient.record_id}</span>
            <Tag>{patient.segs.length} 段</Tag>
            {patient.has_result ? (
              <Tag color="success">已匹配</Tag>
            ) : (
              <Tag color="warning">无结果</Tag>
            )}
          </Space>
        ),
        key: `patient-${patient.id}`,
        isLeaf: true,
      })),
    }))
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h2>数据管理</h2>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic title="日期数" value={dataStatus?.total_dates ?? 0} prefix={<FolderOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="总病历数" value={dataStatus?.total_patients ?? 0} prefix={<CustomerServiceOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已匹配"
              value={dataStatus?.matched_count ?? 0}
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="仅录音"
              value={dataStatus?.audio_only_count ?? 0}
              valueStyle={{ color: '#faad14' }}
              prefix={<WarningOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={16}>
          <Card title="录音文件树" extra={
            <Button icon={<ScanOutlined />} onClick={handleScan}>扫描目录</Button>
          }>
            {loadingTree ? (
              <Spin />
            ) : audioTree.length === 0 ? (
              <Empty description="暂无数据，请先扫描目录或上传结果" />
            ) : (
              <Tree
                showIcon
                defaultExpandAll
                treeData={buildTreeData()}
              />
            )}
          </Card>
        </Col>

        <Col span={8}>
          <Card title="导入 B 超结果">
            <Upload.Dragger
              accept=".xlsx,.xls"
              beforeUpload={handleUpload as any}
              showUploadList={false}
              disabled={uploading}
            >
              <p className="ant-upload-drag-icon">
                <CloudUploadOutlined style={{ fontSize: 32, color: '#1677ff' }} />
              </p>
              <p>点击或拖拽 xlsx 文件到此处上传</p>
              <p style={{ color: '#999', fontSize: 12 }}>
                支持 .xlsx / .xls，自动解析卵泡数、内膜等字段
              </p>
            </Upload.Dragger>

            <div style={{ marginTop: 16 }}>
              <h4>操作说明：</h4>
              <ol style={{ paddingLeft: 20, color: '#666', fontSize: 13 }}>
                <li>点击"扫描目录"同步录音文件结构到数据库</li>
                <li>上传 B 超结果 xlsx，按病历号自动匹配</li>
                <li>匹配成功后即可进入"单条测试"</li>
              </ol>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

// 导入缺失的图标
import { CheckCircleOutlined, WarningOutlined } from '@ant-design/icons'
