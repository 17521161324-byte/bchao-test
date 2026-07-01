/**
 * 主应用入口
 */
import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, App as AntApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import MainLayout from './components/Layout'
import DataImport from './pages/DataImport'
import ModelConfigPage from './pages/ModelConfig'
import SingleTest from './pages/SingleTest'
import Evaluation from './pages/Evaluation'
import TestHistory from './pages/TestHistory'

export default function App() {
  return (
    <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#1677ff' } }}>
      <AntApp>
        <BrowserRouter>
          <Routes>
            <Route element={<MainLayout />}>
              <Route path="/" element={<Navigate to="/data" replace />} />
              <Route path="/data" element={<DataImport />} />
              <Route path="/model" element={<ModelConfigPage />} />
              <Route path="/test" element={<SingleTest />} />
              <Route path="/eval" element={<Evaluation />} />
              <Route path="/history" element={<TestHistory />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  )
}
