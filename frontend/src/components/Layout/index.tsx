/**
 * 主布局 - 侧边导航 + 顶部栏
 */
import React from 'react'
import { Layout, Menu, Badge, Space } from 'antd'
import {
  FolderOutlined,
  SettingOutlined,
  PlayCircleOutlined,
  AuditOutlined,
  HistoryOutlined,
  CloudServerOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAppStore } from '../store'

const { Header, Sider, Content } = Layout

const menuItems = [
  { key: '/data', icon: <FolderOutlined />, label: '数据管理' },
  { key: '/model', icon: <SettingOutlined />, label: '模型配置' },
  { key: '/test', icon: <PlayCircleOutlined />, label: '单条测试' },
  { key: '/eval', icon: <AuditOutlined />, label: '结果评估' },
  { key: '/history', icon: <HistoryOutlined />, label: '测试历史' },
]

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { dataStatus } = useAppStore()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        theme="dark"
        width={220}
        style={{ position: 'sticky', top: 0, height: '100vh', overflow: 'auto' }}
      >
        <div
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: 16,
            fontWeight: 600,
            borderBottom: '1px solid rgba(255,255,255,0.1)',
          }}
        >
          <CloudServerOutlined style={{ marginRight: 8 }} />
          B 超语音测试平台
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <Space>
            <span style={{ color: '#666' }}>
              数据状态：
              {dataStatus ? (
                <>
                  <Badge color="green" /> {dataStatus.matched_count} 已匹配
                  <Badge color="orange" style={{ marginLeft: 8 }} /> {dataStatus.audio_only_count} 仅录音
                </>
              ) : '加载中...'}
            </span>
          </Space>
        </Header>

        <Content style={{ background: '#f5f5f5', minHeight: 'calc(100vh - 64px)' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
