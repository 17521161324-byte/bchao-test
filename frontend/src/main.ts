/**
 * 应用入口
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import router from './router'
import './index.css'

// 全局注册图标，避免在各页面中重复导入
import {
  CloudServerOutlined,
  FolderOutlined,
  SettingOutlined,
  ExperimentOutlined,
  ScanOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  ApiOutlined,
  ArrowLeftOutlined,
  CaretRightOutlined,
  PauseOutlined,
  SearchOutlined,
  LeftOutlined,
  RightOutlined,
} from '@ant-design/icons-vue'

const app = createApp(App)

// 注册图标
const icons = {
  CloudServerOutlined,
  FolderOutlined,
  SettingOutlined,
  ExperimentOutlined,
  ScanOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  ApiOutlined,
  ArrowLeftOutlined,
  CaretRightOutlined,
  PauseOutlined,
  SearchOutlined,
  LeftOutlined,
  RightOutlined,
}
for (const [name, component] of Object.entries(icons)) {
  app.component(name, component)
}

app.use(createPinia())
app.use(router)
app.use(Antd)
app.mount('#app')
