<template>
  <div class="page-container">
    <!-- 筛选区域 -->
    <a-card style="margin-bottom: 16px">
      <a-row :gutter="16" align="middle">
        <a-col :span="16">
          <a-space>
            <span style="color: #666">批次：</span>
            <a-checkable-tag :checked="selectedBatch === null" @click="selectBatch(null)" style="cursor: pointer">全部</a-checkable-tag>
            <a-checkable-tag v-for="batch in batches" :key="batch.date" :checked="selectedBatch === batch.date" @click="selectBatch(batch.date)" style="cursor: pointer">
              {{ formatDate(batch.date) }} ({{ batch.patient_count }}人)
            </a-checkable-tag>
          </a-space>
        </a-col>
        <a-col :span="8">
          <a-input-search v-model:value="searchText" placeholder="搜索病历号" allow-clear />
        </a-col>
      </a-row>
    </a-card>

    <!-- 批量执行区域 -->
    <a-card size="small" title="批量执行" style="margin-bottom: 16px">
      <a-row :gutter="12" align="middle">
        <a-col :span="5">
          <a-select v-model:value="batchAsrModelId" placeholder="选择 ASR 模型" allow-clear style="width: 100%">
            <a-select-option v-for="m in asrModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
          </a-select>
        </a-col>
        <a-col :span="5">
          <a-select v-model:value="batchTemplateId" placeholder="选择提示词模板" allow-clear style="width: 100%" @change="onBatchTemplateChange">
            <a-select-option v-for="t in promptTemplates" :key="t.id" :value="t.id">{{ t.name }}</a-select-option>
          </a-select>
        </a-col>
        <a-col :span="5">
          <a-select v-model:value="batchLlmModelId" placeholder="选择 LLM 模型" allow-clear style="width: 100%">
            <a-select-option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
          </a-select>
        </a-col>
        <a-col :span="9">
          <a-space wrap>
            <a-button type="primary" :disabled="!batchAsrModelId || batchRunning" :loading="batchRunning && batchMode === 'asr'" @click="runBatch('asr')">批量 ASR</a-button>
            <a-button :disabled="!batchLlmModelId || !batchTemplateId || batchRunning" :loading="batchRunning && batchMode === 'llm'" @click="runBatch('llm')">批量 LLM</a-button>
            <a-button type="primary" ghost :disabled="!batchAsrModelId || !batchLlmModelId || !batchTemplateId || batchRunning" :loading="batchRunning && batchMode === 'both'" @click="runBatch('both')">ASR + LLM</a-button>
            <span style="font-size: 12px; color: #666">作用范围：当前筛选 {{ filteredRecords.length }} 条</span>
          </a-space>
        </a-col>
      </a-row>
      <div v-if="batchRunning || batchFailures.length" style="margin-top: 12px">
        <div v-if="batchRunning" style="color: #666; font-size: 12px; margin-bottom: 8px">
          执行中：{{ batchProgress.done }}/{{ batchProgress.total }}
          成功 {{ batchProgress.success }} 条，失败 {{ batchProgress.failed }} 条
          <span v-if="batchProgress.current">，当前：{{ batchProgress.current }}</span>
        </div>
        <div v-if="batchFailures.length" style="border: 1px solid #ffccc7; border-radius: 6px; background: #fff2f0; padding: 8px 12px; margin-top: 8px">
          <div style="font-weight: 600; color: #ff4d4f; font-size: 12px; margin-bottom: 6px">
            失败明细 ({{ batchFailures.length }} 条):
          </div>
          <div style="max-height: 120px; overflow-y: auto">
            <div v-for="(f, i) in batchFailures" :key="i" style="font-size: 11px; color: #333; padding: 2px 0">
              <span style="color: #ff4d4f">[{{ f.stage }}]</span>
              {{ f.record_id }} / {{ f.date }} — {{ f.error }}
            </div>
          </div>
        </div>
      </div>
    </a-card>

    <!-- 数据表格 -->
    <a-card>
      <a-table :data-source="filteredRecords" :loading="loadingTree" :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }" size="small" :custom-row="onRowClick" row-key="id" :scroll="{ x: 'max-content' }">
        <a-table-column title="病历号" data-index="record_id" :width="120" />
        <a-table-column title="日期" data-index="date" :width="120">
          <template #default="{ record }">{{ formatDate(record.date) }}</template>
        </a-table-column>
        <a-table-column title="录音" :width="100">
          <template #default="{ record }">
            <a-tag v-if="record.has_audio" color="green">有 ({{ record.segs?.length || 0 }}段)</a-tag>
            <a-tag v-else color="red">无</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="结果" :width="100">
          <template #default="{ record }">
            <a-tag v-if="record.has_result" color="green">有</a-tag>
            <a-tag v-else color="default">无</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="ASR模型" :width="150">
          <template #default="{ record }">
            <a-tag :color="getListAsrStatusColor(record)">{{ getListAsrStatusText(record) }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="LLM状态" :width="150">
          <template #default="{ record }">
            <a-tag :color="getLlmStatusColor(record)">{{ getLlmStatusText(record) }}</a-tag>
            <div v-if="record.latest_llm" style="font-size: 12px; color: #666; margin-top: 4px">
              <span style="color: #1890ff">{{ record.latest_llm.asr_model_name || record.latest_llm.asr_source || '-' }}</span>
              <span style="margin: 0 2px">+</span>
              <span>{{ record.latest_llm.llm_model_name || '-' }}</span>
              <span v-if="record.latest_llm.prompt_template_name"> / {{ record.latest_llm.prompt_template_name }}</span>
            </div>
            <div v-else-if="record.latest_asr" style="font-size: 12px; color: #999; margin-top: 4px">
              ASR: {{ record.latest_asr.asr_model_name || '-' }}
            </div>
          </template>
        </a-table-column>
        <a-table-column title="准确率" :width="90" align="center">
          <template #default="{ record }">{{ formatAccuracy(record.latest_llm?.accuracy) }}</template>
        </a-table-column>
        <a-table-column title="右卵泡" :width="80" align="center">
          <template #default="{ record }"><a-tag :color="matchTagColor(getMatchStatus(record, 'right_follicle'))">{{ matchTagText(getMatchStatus(record, 'right_follicle')) }}</a-tag></template>
        </a-table-column>
        <a-table-column title="左卵泡" :width="80" align="center">
          <template #default="{ record }"><a-tag :color="matchTagColor(getMatchStatus(record, 'left_follicle'))">{{ matchTagText(getMatchStatus(record, 'left_follicle')) }}</a-tag></template>
        </a-table-column>
        <a-table-column title="内膜厚度" :width="90" align="center">
          <template #default="{ record }"><a-tag :color="matchTagColor(getMatchStatus(record, 'endometrium_thickness'))">{{ matchTagText(getMatchStatus(record, 'endometrium_thickness')) }}</a-tag></template>
        </a-table-column>
        <a-table-column title="内膜类型" :width="90" align="center">
          <template #default="{ record }"><a-tag :color="matchTagColor(getMatchStatus(record, 'endometrium_type'))">{{ matchTagText(getMatchStatus(record, 'endometrium_type')) }}</a-tag></template>
        </a-table-column>
        <a-table-column title="右卵巢" :width="80" align="center">
          <template #default="{ record }"><a-tag :color="matchTagColor(getMatchStatus(record, 'right_ovary'))">{{ matchTagText(getMatchStatus(record, 'right_ovary')) }}</a-tag></template>
        </a-table-column>
        <a-table-column title="左卵巢" :width="80" align="center">
          <template #default="{ record }"><a-tag :color="matchTagColor(getMatchStatus(record, 'left_ovary'))">{{ matchTagText(getMatchStatus(record, 'left_ovary')) }}</a-tag></template>
        </a-table-column>
        <a-table-column title="操作" :width="100">
          <template #default="{ record }">
            <a-button size="small" type="link" @click.stop="openDetail(record)">详情</a-button>
          </template>
        </a-table-column>
      </a-table>
    </a-card>

    <!-- 详情抽屉 -->
    <a-drawer :open="drawerOpen" title="检查详情" placement="right" width="90vw" @close="closeDrawer">
      <template v-if="selectedRecord">
        <!-- 顶部描述区域 -->
        <a-descriptions :column="4" bordered size="small" style="margin-bottom: 16px">
          <a-descriptions-item label="病历号">{{ selectedRecord.record_id }}</a-descriptions-item>
          <a-descriptions-item label="日期">{{ formatDate(selectedRecord.date) }}</a-descriptions-item>
          <a-descriptions-item label="录音分段">{{ selectedRecord.segs?.length || 0 }} 段</a-descriptions-item>
          <a-descriptions-item label="B超结果">
            <a-tag v-if="selectedRecord.result" color="green">有</a-tag>
            <a-tag v-else color="default">无</a-tag>
          </a-descriptions-item>
        </a-descriptions>

        <!-- ASR + LLM 并行双列布局 -->
        <a-row :gutter="16" style="margin-bottom: 16px">
          <!-- ============ 左列：ASR (多模型) ============ -->
          <a-col :span="12">
            <a-card size="small" style="margin-bottom: 16px; height: 100%">
              <template #title>
                <span>语音转写 (ASR)</span>
                <a-tag v-if="selectedAsrResult" color="blue" style="margin-left: 8px">{{ selectedAsrResult.model_name }}</a-tag>
              </template>
              <template #extra>
                <a-space :size="4">
                  <a-button type="primary" size="small" @click="runAsr" :loading="asrRunning">
                    <template #icon><ScanOutlined /></template>
                    {{ asrRunning ? '转写中...' : (currentAsrStatus === 'success' ? '重新识别' : '开始识别') }}
                  </a-button>
                  <span v-if="asrProgress" style="font-size: 12px; color: #666; margin-left: 8px">
                    处理中 {{ asrProgress.seg_index }} / {{ asrProgress.total }}
                  </span>
                </a-space>
              </template>

              <!-- ASR 模型选择 -->
              <div style="margin-bottom: 12px">
                <span style="font-size: 12px; color: #666; margin-right: 8px">模型:</span>
                <a-checkable-tag
                  v-for="m in asrModels"
                  :key="m.id"
                  :checked="asrModelId === m.id"
                  @click="selectAsrModel(m)"
                  style="cursor: pointer; margin-right: 4px"
                  :color="getAsrModelStatusColor(m.id)"
                >
                  {{ m.name }} · {{ getAsrModelStatusText(m.id) }}
                </a-checkable-tag>
              </div>

              <!-- 播放器 -->
              <AudioPlayer v-if="selectedRecord.segs?.length" :segs="selectedRecord.segs" style="margin-bottom: 12px" />

              <!-- ASR 结果 -->
              <div v-if="selectedAsrResult" style="max-height: 360px; overflow-y: auto">
                <div v-if="selectedAsrResult.status === 'failed'" style="color: #ff4d4f; margin-bottom: 8px; font-size: 12px">
                  转写失败: {{ selectedAsrResult.error_message || '未知错误' }}
                </div>
                <div style="font-size: 13px; color: #666; margin-bottom: 4px">转写结果：</div>
                <div style="background: #f5f5f5; padding: 12px; border-radius: 6px; font-size: 14px; line-height: 1.8; white-space: pre-wrap">{{ selectedAsrResult.full_transcript || '(无内容)' }}</div>
              </div>
              <a-empty v-else description="暂无转写结果" style="padding: 20px 0" />
            </a-card>
          </a-col>

          <!-- ============ 右列：LLM ============ -->
          <a-col :span="12">
            <a-card size="small" style="margin-bottom: 16px; height: 100%">
              <template #title>
                <span>LLM 结构化提取</span>
                <a-tag v-if="selectedAsrResult" color="blue" style="margin-left: 8px">ASR: {{ selectedAsrResult.model_name }}</a-tag>
                <a-tag v-if="llmResult" color="purple" style="margin-left: 8px">{{ llmResult.model_name }}</a-tag>
              </template>
              <template #extra>
                <a-space :size="4">
                  <a-select
                    v-model:value="selectedTemplateId"
                    placeholder="选择模版"
                    style="width: 140px"
                    size="small"
                    allow-clear
                    @change="onTemplateChange"
                  >
                    <a-select-option v-for="t in promptTemplates" :key="t.id" :value="t.id">{{ t.name }}</a-select-option>
                  </a-select>
                  <a-select v-model:value="llmModelId" style="width: 140px" size="small" placeholder="LLM模型" allow-clear>
                    <a-select-option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
                  </a-select>
                  <a-button type="primary" size="small" @click="runLlm" :loading="llmRunning" :disabled="!selectedAsrResult">
                    <template #icon><RobotOutlined /></template>
                    {{ llmRunning ? '提取中...' : '开始提取' }}
                  </a-button>
                  <a-button type="link" size="small" @click="showTemplateModal = true">模版</a-button>
                </a-space>
              </template>

              <!-- LLM 结果 (含历史记录 Tab) -->
              <a-tabs v-model:activeKey="llmTab" size="small">
                <a-tab-pane key="current" tab="当前结果">
                  <div v-if="llmResult" style="padding-top: 12px">
                    <!-- A. 顶部: 模型 + 导出 -->
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
                      <a-space>
                        <a-tag color="purple">{{ llmResult.model_name }}</a-tag>
                        <a-tag v-if="selectedAsrResult" color="blue">ASR: {{ selectedAsrResult.model_name }}</a-tag>
                        <a-tag v-if="llmResult.accuracy != null" :color="llmResult.accuracy >= 0.8 ? 'green' : 'orange'">
                          {{ (llmResult.accuracy * 100).toFixed(0) }}%
                        </a-tag>
                      </a-space>
                      <a-space>
                        <a-button size="small" @click="exportCurrentLlmHistory">导出Excel</a-button>
                        <a-button size="small" type="link" @click="showLlmDetailModal = true">完整数据</a-button>
                      </a-space>
                    </div>

                    <!-- B. LLM 转写/总结内容 -->
                    <a-card size="small" style="margin-bottom: 12px">
                      <template #title><span style="font-size: 12px">LLM 转写/总结</span></template>
                      <div v-if="llmDisplayText" class="llm-summary-box">{{ llmDisplayText }}</div>
                      <a-empty v-else description="暂无 LLM 总结内容" style="padding: 12px 0" />
                    </a-card>

                  </div>
                  <a-empty v-else description="请先完成 ASR 转写并提取 LLM" style="padding: 20px 0" />
                </a-tab-pane>

                <a-tab-pane key="history" :tab="`历史记录 (${llmHistory.length})`">
                  <div style="padding-top: 12px">
                    <a-space style="margin-bottom: 12px">
                      <a-button
                        size="small"
                        :disabled="!llmHistory.length"
                        @click="exportCurrentLlmHistory"
                      >
                        <template #icon><RobotOutlined /></template>
                        导出 Excel
                      </a-button>
                      <a-button
                        size="small"
                        danger
                        :disabled="!llmHistory.length"
                        @click="showClearConfirm = true"
                      >
                        清空历史
                      </a-button>
                    </a-space>
                    <a-table
                      :data-source="llmHistory"
                      :loading="false"
                      size="small"
                      row-key="id"
                      :pagination="{ pageSize: 10 }"
                      :scroll="{ x: 800 }"
                    >
                      <a-table-column title="时间" :width="95">
                        <template #default="{ record }">{{ formatShortDateTime(record.created_at) }}</template>
                      </a-table-column>
                      <a-table-column title="ASR模型" :width="120">
                        <template #default="{ record }">
                          <a-tooltip :title="record.asr_model_name || '-'">
                            <span class="table-ellipsis">{{ record.asr_model_name || '-' }}</span>
                          </a-tooltip>
                        </template>
                      </a-table-column>
                      <a-table-column title="LLM模型" :width="120">
                        <template #default="{ record }">
                          <a-tooltip :title="record.model_name || record.llm_model_name || '-'">
                            <span class="table-ellipsis">{{ record.model_name || record.llm_model_name || '-' }}</span>
                          </a-tooltip>
                        </template>
                      </a-table-column>
                      <a-table-column title="提示词模板" :width="160">
                        <template #default="{ record }">
                          <a-tooltip :title="record.prompt_template_name || '未记录'">
                            <span class="table-ellipsis">{{ record.prompt_template_name || '-' }}</span>
                          </a-tooltip>
                        </template>
                      </a-table-column>
                      <a-table-column title="状态" :width="60" align="center">
                        <template #default="{ record }">
                          <CheckCircleOutlined v-if="record.status === 'success'" style="color: #52c41a" />
                          <CloseCircleOutlined v-else-if="record.status === 'failed'" style="color: #ff4d4f" />
                          <Spin v-else size="small" />
                        </template>
                      </a-table-column>
                      <a-table-column title="准确率" :width="70" align="center">
                        <template #default="{ record }">{{ record.accuracy != null ? (record.accuracy * 100).toFixed(0) + '%' : '-' }}</template>
                      </a-table-column>
                      <a-table-column title="查看" :width="70" align="center">
                        <template #default="{ record }">
                          <a-button size="small" type="link" @click="viewLlmHistory(record)"><EyeOutlined /></a-button>
                        </template>
                      </a-table-column>
                    </a-table>
                  </div>
                </a-tab-pane>
              </a-tabs>
            </a-card>
          </a-col>
        </a-row>

        <!-- ==================== 卵泡明细 + B 超结果 并行显示 ==================== -->
        <a-divider>卵泡明细对比</a-divider>
        <a-row :gutter="16">
          <!-- LLM 卵泡结果 -->
          <a-col :span="12">
            <a-card size="small" title="LLM 提取结果 (来源:LLM结构化结果)" style="margin-bottom: 16px">
              <template #extra>
                <a-tag v-if="llmResult" color="purple">{{ llmResult.model_name }}</a-tag>
              </template>
              <div v-if="llmResult">
                <a-row :gutter="12" style="margin-bottom: 12px">
                  <a-col :span="12">
                    <a-card size="small" title="右侧卵泡" style="margin-bottom: 8px">
                      <div style="font-size: 22px; font-weight: bold">
                        {{ normalizedLlmStructured?.right_follicle_total ?? '-' }}
                        <span style="font-size: 14px; font-weight: normal">个</span>
                        <CheckCircleOutlined v-if="compareField('right_follicle_total', true)" style="color: #52c41a; margin-left: 4px" />
                        <CloseCircleOutlined v-else-if="compareField('right_follicle_total', false)" style="color: #ff4d4f; margin-left: 4px" />
                      </div>
                      <div class="follicle-list">
                        <span v-for="(f, i) in rightFollCompare" :key="'r'+i" class="follicle-item" :class="'status-' + f.status">
                          {{ f.size }}×{{ f.count }}
                        </span>
                        <span v-if="!rightFollCompare.length" style="color: #666; font-size: 12px">-</span>
                      </div>
                    </a-card>
                  </a-col>
                  <a-col :span="12">
                    <a-card size="small" title="左侧卵泡" style="margin-bottom: 8px">
                      <div style="font-size: 22px; font-weight: bold">
                        {{ normalizedLlmStructured?.left_follicle_total ?? '-' }}
                        <span style="font-size: 14px; font-weight: normal">个</span>
                        <CheckCircleOutlined v-if="compareField('left_follicle_total', true)" style="color: #52c41a; margin-left: 4px" />
                        <CloseCircleOutlined v-else-if="compareField('left_follicle_total', false)" style="color: #ff4d4f; margin-left: 4px" />
                      </div>
                      <div class="follicle-list">
                        <span v-for="(f, i) in leftFollCompare" :key="'l'+i" class="follicle-item" :class="'status-' + f.status">
                          {{ f.size }}×{{ f.count }}
                        </span>
                        <span v-if="!leftFollCompare.length" style="color: #666; font-size: 12px">-</span>
                      </div>
                    </a-card>
                  </a-col>
                </a-row>
                <a-descriptions :column="2" bordered size="small">
                  <a-descriptions-item label="内膜厚度">
                    <span :style="{ color: compareField('endometrium_thickness', true) ? '#52c41a' : (compareField('endometrium_thickness', false) ? '#ff4d4f' : 'inherit') }">
                      {{ llmResult.structured?.endometrium_thickness != null ? llmResult.structured.endometrium_thickness + ' mm' : '-' }}
                    </span>
                  </a-descriptions-item>
                  <a-descriptions-item label="内膜类型">
                    <span :style="{ color: compareField('endometrium_type', true) ? '#52c41a' : (compareField('endometrium_type', false) ? '#ff4d4f' : 'inherit') }">
                      {{ llmResult.structured?.endometrium_type || '-' }}
                    </span>
                  </a-descriptions-item>
                  <a-descriptions-item label="右卵巢">
                    {{ llmResult.structured?.right_ovary_length && llmResult.structured?.right_ovary_width ? `${llmResult.structured.right_ovary_length} × ${llmResult.structured.right_ovary_width} mm` : '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item label="左卵巢">
                    {{ llmResult.structured?.left_ovary_length && llmResult.structured?.left_ovary_width ? `${llmResult.structured.left_ovary_length} × ${llmResult.structured.left_ovary_width} mm` : '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item label="备注" :span="2">
                    {{ llmResult.structured?.remark || '-' }}
                  </a-descriptions-item>
                </a-descriptions>
              </div>
              <a-empty v-else description="请先完成 LLM 提取" style="padding: 20px 0" />
            </a-card>
          </a-col>

          <!-- B 超真实结果 -->
          <a-col :span="12">
            <a-card size="small" title="B 超检查结果 (来源:原始检查结果)" style="margin-bottom: 16px" v-if="selectedRecord.result">
              <template #extra>
                <a-button size="small" type="link" @click="openEditBUltra">编辑真实结果</a-button>
              </template>
              <a-row :gutter="12" style="margin-bottom: 12px">
                <a-col :span="12">
                  <a-card size="small" title="右侧卵泡" style="margin-bottom: 8px">
                    <div style="font-size: 22px; font-weight: bold">{{ selectedRecord.result.right_follicle_total }} 个</div>
                    <div class="follicle-list">
                      <template v-if="rightGtFolls.length">
                        <span v-for="(f, i) in rightGtFolls" :key="'rg'+i" class="follicle-item" :class="gtFollClass(f.size, 'right', f.count)">
                          {{ f.size }}×{{ f.count }}
                        </span>
                      </template>
                      <span v-else style="color: #666; font-size: 12px">-</span>
                    </div>
                  </a-card>
                </a-col>
                <a-col :span="12">
                  <a-card size="small" title="左侧卵泡" style="margin-bottom: 8px">
                    <div style="font-size: 22px; font-weight: bold">{{ selectedRecord.result.left_follicle_total }} 个</div>
                    <div class="follicle-list">
                      <template v-if="leftGtFolls.length">
                        <span v-for="(f, i) in leftGtFolls" :key="'lg'+i" class="follicle-item" :class="gtFollClass(f.size, 'left', f.count)">
                          {{ f.size }}×{{ f.count }}
                        </span>
                      </template>
                      <span v-else style="color: #666; font-size: 12px">-</span>
                    </div>
                  </a-card>
                </a-col>
              </a-row>
              <a-descriptions :column="2" bordered size="small">
                <a-descriptions-item label="内膜厚度">
                  {{ selectedRecord.result.endometrium_thickness != null ? selectedRecord.result.endometrium_thickness + ' mm' : '-' }}
                </a-descriptions-item>
                <a-descriptions-item label="内膜类型">{{ selectedRecord.result.endometrium_type || '-' }}</a-descriptions-item>
                <a-descriptions-item label="右卵巢">
                  {{ selectedRecord.result.right_ovary_length && selectedRecord.result.right_ovary_width ? `${selectedRecord.result.right_ovary_length} × ${selectedRecord.result.right_ovary_width} mm` : '-' }}
                </a-descriptions-item>
                <a-descriptions-item label="左卵巢">
                  {{ selectedRecord.result.left_ovary_length && selectedRecord.result.left_ovary_width ? `${selectedRecord.result.left_ovary_length} × ${selectedRecord.result.left_ovary_width} mm` : '-' }}
                </a-descriptions-item>
                <a-descriptions-item label="备注" :span="2" v-if="selectedRecord.result.remark">{{ selectedRecord.result.remark }}</a-descriptions-item>
              </a-descriptions>
            </a-card>
            <a-card v-else size="small" title="B 超检查结果" style="margin-bottom: 16px">
              <template #extra>
                <a-button size="small" type="link" @click="openEditBUltra">新增真实结果</a-button>
              </template>
              <a-empty description="该检查记录无 B 超结果" style="padding: 20px 0" />
            </a-card>
          </a-col>
        </a-row>
      </template>
    </a-drawer>

    <!-- 编辑真实 B 超结果弹窗 -->
    <a-modal
      v-model:open="showBUltraModal"
      :title="selectedRecord?.result ? '编辑真实 B 超结果' : '新增真实 B 超结果'"
      width="600px"
      :confirm-loading="bUltraSaving"
      @ok="saveBUltraResult"
      @cancel="showBUltraModal = false"
    >
      <a-form layout="vertical" size="small">
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="右侧卵泡总数"><a-input-number v-model:value="bUltraForm.right_follicle_total" style="width: 100%" placeholder="自动求和" /></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="左侧卵泡总数"><a-input-number v-model:value="bUltraForm.left_follicle_total" style="width: 100%" placeholder="自动求和" /></a-form-item></a-col>
        </a-row>
        <a-form-item label="右侧卵泡明细"><a-textarea v-model:value="bUltraForm.right_follicles_raw" :rows="3" placeholder="10x2&#10;12×1" /></a-form-item>
        <a-form-item label="左侧卵泡明细"><a-textarea v-model:value="bUltraForm.left_follicles_raw" :rows="3" /></a-form-item>
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="内膜厚度"><a-input-number v-model:value="bUltraForm.endometrium_thickness" style="width: 100%" /></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="内膜类型"><a-select v-model:value="bUltraForm.endometrium_type" allow-clear><a-select-option value="A">A</a-select-option><a-select-option value="B">B</a-select-option><a-select-option value="C">C</a-select-option></a-select></a-form-item></a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="右卵巢长"><a-input-number v-model:value="bUltraForm.right_ovary_length" style="width: 100%" /></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="右卵巢宽"><a-input-number v-model:value="bUltraForm.right_ovary_width" style="width: 100%" /></a-form-item></a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="12"><a-form-item label="左卵巢长"><a-input-number v-model:value="bUltraForm.left_ovary_length" style="width: 100%" /></a-form-item></a-col>
          <a-col :span="12"><a-form-item label="左卵巢宽"><a-input-number v-model:value="bUltraForm.left_ovary_width" style="width: 100%" /></a-form-item></a-col>
        </a-row>
        <a-form-item label="备注"><a-textarea v-model:value="bUltraForm.remark" :rows="2" /></a-form-item>
      </a-form>
    </a-modal>

    <!-- 提示词模版管理弹窗 -->
    <a-modal
      v-model:open="showTemplateModal"
      title="提示词模版管理"
      width="1000px"
      :footer="null"
      destroy-on-close
    >
      <a-row :gutter="16">
        <!-- 左侧:模版列表 -->
        <a-col :span="6">
          <a-button type="primary" size="small" style="margin-bottom: 12px" @click="createNewTemplate">
            <template #icon><PlusOutlined /></template>
            新增模版
          </a-button>
          <a-list
            :data-source="promptTemplates"
            :loading="templateLoading"
            size="small"
            bordered
            style="max-height: 560px; overflow-y: auto"
          >
            <template #renderItem="{ item }">
              <a-list-item
                :style="{ background: selectedTemplateId === item.id ? '#e6f7ff' : 'transparent', cursor: 'pointer' }"
                @click="selectTemplate(item.id)"
              >
                <a-list-item-meta>
                  <template #title>
                    <span>{{ item.name }}</span>
                    <a-tag v-if="item.is_default" color="gold" style="margin-left: 4px">默认</a-tag>
                  </template>
                  <template #description>
                    <div style="color: #999; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: pre-wrap; max-height: 40px">
                      {{ item.content }}
                    </div>
                  </template>
                </a-list-item-meta>
              </a-list-item>
            </template>
          </a-list>
        </a-col>

        <!-- 右侧:模版详情/编辑 + 预览 -->
        <a-col :span="18">
          <a-form layout="vertical" size="small">
            <a-form-item label="模版名称" required>
              <a-input v-model:value="templateForm.name" placeholder="如：B超提取模版 v2" />
            </a-form-item>
            <a-form-item>
              <a-switch v-model:checked="templateForm.is_default" checked-children="默认" un-checked-children="非默认" />
            </a-form-item>

            <a-tabs v-model:activeKey="templateTab" size="small">
              <a-tab-pane key="edit" tab="编辑">
                <a-textarea
                  v-model:value="templateForm.content"
                  :rows="18"
                  placeholder="# 角色...&#10;## 任务...&#10;{transcript}"
                  style="font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 13px"
                />
              </a-tab-pane>
              <a-tab-pane key="preview" tab="预览">
                <div class="markdown-preview" v-html="templatePreviewHtml"></div>
              </a-tab-pane>
            </a-tabs>

            <a-form-item style="margin-top: 12px">
              <a-space>
                <a-button type="primary" :loading="templateSaving" @click="saveTemplate">保存</a-button>
                <a-button :disabled="!templateForm.id" danger @click="deleteTemplate(templateForm.id)">删除</a-button>
                <a-button type="link" :disabled="!templateForm.content" @click="applyTemplateToCurrent">应用到当前检查</a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-col>
      </a-row>
    </a-modal>

    <!-- LLM 完整数据弹窗 -->
    <a-modal
      v-model:open="showLlmDetailModal"
      title="LLM 完整数据"
      width="900px"
      :footer="null"
    >
      <div v-if="currentLlmResult">
        <!-- 基本信息 -->
        <a-descriptions :column="3" bordered size="small" style="margin-bottom: 16px">
          <a-descriptions-item label="模型">{{ currentLlmResult.model_name }}</a-descriptions-item>
          <a-descriptions-item label="准确率">{{ currentLlmResult.accuracy != null ? (currentLlmResult.accuracy * 100).toFixed(0) + '%' : '-' }}</a-descriptions-item>
          <a-descriptions-item label="状态">{{ currentLlmResult.status }}</a-descriptions-item>
        </a-descriptions>

        <!--结构化结果 -->
        <a-card size="small" style="margin-bottom: 16px">
          <template #title><span style="font-size: 12px">结构化结果 (structured)</span></template>
          <pre style="background: #f5f5f5; padding: 12px; border-radius: 4px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow-y: auto">{{ JSON.stringify(currentLlmResult.structured || currentLlmResult.structured_result, null, 2) }}</pre>
        </a-card>

        <!-- summary / raw_output -->
        <a-card size="small" style="margin-bottom: 16px">
          <template #title><span style="font-size: 12px">总结/原始输出</span></template>
          <pre style="background: #f5f5f5; padding: 12px; border-radius: 4px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow-y: auto">{{ currentLlmResult.summary_text || currentLlmResult.summary || currentLlmResult.raw_text || currentLlmResult.raw_output || '(空)' }}</pre>
        </a-card>

        <!-- 评估结果 -->
        <a-card size="small" v-if="currentLlmResult.evaluation">
          <template #title><span style="font-size: 12px">评估结果</span></template>
          <pre style="background: #f5f5f5; padding: 12px; border-radius: 4px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto">{{ JSON.stringify(currentLlmResult.evaluation, null, 2) }}</pre>
        </a-card>
      </div>
    </a-modal>

    <!-- 清空历史确认弹窗 -->
    <a-modal
      v-model:open="showClearConfirm"
      title="确认清空历史"
      ok-text="确认清空"
      cancel-text="取消"
      :ok-button-props="{ danger: true }"
      :confirm-loading="clearing"
      @ok="confirmClearLlmHistory"
      @cancel="showClearConfirm = false"
    >
      <p style="color: #ff4d4f; font-weight: 600">⚠ 此操作不可恢复!</p>
      <p>确认清空当前检查记录的全部 LLM 历史记录吗?</p>
      <p style="color: #666; font-size: 12px">
        病历号: {{ selectedRecord?.record_id || '-' }} |
        当前历史数: {{ llmHistory.length }} 条
      </p>
    </a-modal>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, computed, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  ScanOutlined, RobotOutlined, CheckCircleOutlined, CloseCircleOutlined, SettingOutlined, PlusOutlined, EyeOutlined, EditOutlined,
} from '@ant-design/icons-vue'
import { useAppStore } from '@/stores'
import { resultApi, modelApi, testApi, promptTemplateApi, patientApi } from '@/api/client'
import type { PatientExamination, BUltraResult } from '@/types'
import AudioPlayer from '@/components/AudioPlayer/index.vue'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

export default defineComponent({
  name: 'DataImport',
  components: { AudioPlayer },
  setup() {
    const store = useAppStore()
    const searchText = ref('')

    const drawerOpen = computed(() => store.drawerOpen)
    const selectedRecord = computed(() => store.selectedRecord)
    const batches = computed(() => store.batches)
    const selectedBatch = computed(() => store.selectedBatch)
    const loadingTree = computed(() => store.loadingTree)
    const allRecords = computed(() => store.records)

    const filteredRecords = computed(() => {
      if (!searchText.value.trim()) return allRecords.value
      const q = searchText.value.trim().toLowerCase()
      return allRecords.value.filter((r) => r.record_id.toLowerCase().includes(q))
    })

    function selectBatch(date: string | null) { store.selectBatch(date) }
    function openDetail(record: PatientExamination) {
  store.openDrawer(record)
}
    function closeDrawer() { store.closeDrawer() }
    function onRowClick(record: PatientExamination) {
      return { onClick: () => openDetail(record), style: { cursor: 'pointer' } }
    }

    type MatchStatus = 'match' | 'mismatch' | 'empty'

    function getLlmStatusColor(record: PatientExamination): string {
      const status = record.latest_llm?.status
      if (!status) return 'default'
      if (status === 'success') return 'green'
      if (status === 'failed') return 'red'
      if (status === 'running') return 'blue'
      return 'default'
    }

    function getLlmStatusText(record: PatientExamination): string {
      const status = record.latest_llm?.status
      if (!status) return '未提取'
      if (status === 'success') return '已提取'
      if (status === 'failed') return '失败'
      if (status === 'running') return '处理中'
      return status
    }

    function getListAsrStatusColor(record: PatientExamination): string {
      const status = record.latest_asr?.status
      if (!status) return 'default'
      if (status === 'success') return 'blue'
      if (status === 'failed') return 'red'
      if (status === 'running') return 'orange'
      return 'default'
    }

    function getListAsrStatusText(record: PatientExamination): string {
      const asr = record.latest_asr
      if (!asr) return '未转写'
      const name = asr.asr_model_name || 'ASR'
      if (asr.status === 'success') return name
      if (asr.status === 'failed') return `${name} / 失败`
      if (asr.status === 'running') return `${name} / 转写中`
      return name
    }

    function formatAccuracy(value?: number | null): string {
      if (value == null || Number.isNaN(Number(value))) return '-'
      return `${(Number(value) * 100).toFixed(1)}%`
    }

    function fieldMatch(record: PatientExamination, field: string): MatchStatus {
      const item = record.latest_llm?.evaluation?.fields?.[field]
      if (item?.match != null) return item.match ? 'match' : 'mismatch'
      return computeLocalFieldMatch(record, field)
    }

    function mergeStatus(statuses: MatchStatus[]): MatchStatus {
      const valid = statuses.filter((s) => s !== 'empty')
      if (!valid.length) return 'empty'
      return valid.every((s) => s === 'match') ? 'match' : 'mismatch'
    }

    function getMatchStatus(record: PatientExamination, group: string): MatchStatus {
      if (!record.latest_llm || !record.result) return 'empty'
      if (group === 'right_follicle') {
        const detail = fieldMatch(record, 'right_follicles')
        return detail !== 'empty' ? detail : fieldMatch(record, 'right_follicle_total')
      }
      if (group === 'left_follicle') {
        const detail = fieldMatch(record, 'left_follicles')
        return detail !== 'empty' ? detail : fieldMatch(record, 'left_follicle_total')
      }
      if (group === 'right_ovary') {
        return mergeStatus([fieldMatch(record, 'right_ovary_length'), fieldMatch(record, 'right_ovary_width')])
      }
      if (group === 'left_ovary') {
        return mergeStatus([fieldMatch(record, 'left_ovary_length'), fieldMatch(record, 'left_ovary_width')])
      }
      return fieldMatch(record, group)
    }

    function matchTagColor(status: MatchStatus): string {
      if (status === 'match') return 'green'
      if (status === 'mismatch') return 'red'
      return 'default'
    }

    function matchTagText(status: MatchStatus): string {
      if (status === 'match') return '✅'
      if (status === 'mismatch') return '❌'
      return '-'
    }

    function computeLocalFieldMatch(record: PatientExamination, field: string): MatchStatus {
      if (!record.latest_llm?.structured_result || !record.result) return 'empty'
      const structured = normalizeStructured(record.latest_llm.structured_result)
      const gt = record.result as any
      if (!structured) return 'empty'

      if (field === 'right_follicles' || field === 'left_follicles') {
        const llmList = normalizeFollicles(structured[field])
        const gtList = normalizeFollicles(gt[field])
        if (!llmList.length && !gtList.length) return 'empty'
        return JSON.stringify(llmList) === JSON.stringify(gtList) ? 'match' : 'mismatch'
      }

      const llmVal = (structured as any)[field]
      const gtVal = gt[field]
      if (llmVal == null || gtVal == null) return 'empty'
      return String(llmVal).trim() === String(gtVal).trim() ? 'match' : 'mismatch'
    }

    // ======= 真实 B 超结果编辑 =======
    const showBUltraModal = ref(false)
    const bUltraSaving = ref(false)
    const bUltraForm = reactive<any>({
      right_follicle_total: null,
      left_follicle_total: null,
      right_follicles: [],
      left_follicles: [],
      right_follicles_raw: '',
      left_follicles_raw: '',
      endometrium_thickness: null,
      endometrium_type: null,
      right_ovary_length: null,
      right_ovary_width: null,
      left_ovary_length: null,
      left_ovary_width: null,
      remark: '',
    })

    function openEditBUltra() {
      const r = selectedRecord.value?.result || {}
      bUltraForm.right_follicle_total = r.right_follicle_total ?? null
      bUltraForm.left_follicle_total = r.left_follicle_total ?? null
      bUltraForm.right_follicles = r.right_follicles || []
      bUltraForm.left_follicles = r.left_follicles || []
      bUltraForm.right_follicles_raw = (r.right_follicles || []).map((f: any) => `${f.size}x${f.count}`).join('\n')
      bUltraForm.left_follicles_raw = (r.left_follicles || []).map((f: any) => `${f.size}x${f.count}`).join('\n')
      bUltraForm.endometrium_thickness = r.endometrium_thickness ?? null
      bUltraForm.endometrium_type = r.endometrium_type || null
      bUltraForm.right_ovary_length = r.right_ovary_length ?? null
      bUltraForm.right_ovary_width = r.right_ovary_width ?? null
      bUltraForm.left_ovary_length = r.left_ovary_length ?? null
      bUltraForm.left_ovary_width = r.left_ovary_width ?? null
      bUltraForm.remark = r.remark || ''
      showBUltraModal.value = true
    }

    function parseFollicleLines(raw: string): { size: string; count: number }[] {
      if (!raw || !raw.trim()) return []
      const lines = raw.split('\n').map((l) => l.trim()).filter(Boolean)
      const result: { size: string; count: number }[] = []
      for (const line of lines) {
        const m = line.match(/^([\d.]+)\s*[x×*\s]\s*(\d+)$/)
        if (m) {
          result.push({ size: m[1], count: parseInt(m[2], 10) })
        } else {
          throw new Error(`无法解析行: "${line}"，请使用格式如 10x2、12×1、15*3`)
        }
      }
      return result
    }

    async function saveBUltraResult() {
      if (!selectedRecord.value) return
      bUltraSaving.value = true
      try {
        let right_follicles: any[] = []
        let left_follicles: any[] = []
        try {
          right_follicles = parseFollicleLines(bUltraForm.right_follicles_raw)
          left_follicles = parseFollicleLines(bUltraForm.left_follicles_raw)
        } catch (e: any) {
          message.error(e.message)
          bUltraSaving.value = false
          return
        }

        const payload: any = {
          right_follicles,
          left_follicles,
          endometrium_thickness: bUltraForm.endometrium_thickness || null,
          endometrium_type: bUltraForm.endometrium_type || null,
          right_ovary_length: bUltraForm.right_ovary_length || null,
          right_ovary_width: bUltraForm.right_ovary_width || null,
          left_ovary_length: bUltraForm.left_ovary_length || null,
          left_ovary_width: bUltraForm.left_ovary_width || null,
          remark: bUltraForm.remark || null,
        }
        payload.right_follicle_total = bUltraForm.right_follicle_total ?? right_follicles.reduce((s, f) => s + f.count, 0)
        payload.left_follicle_total = bUltraForm.left_follicle_total ?? left_follicles.reduce((s, f) => s + f.count, 0)

        const examRecordId = selectedRecord.value.id
        const res: any = await resultApi.updateBUltraResult(examRecordId, payload)
        const updated = res?.data || res
        message.success('真实 B 超结果已保存')
        showBUltraModal.value = false
        selectedRecord.value = { ...selectedRecord.value, result: updated }
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '保存失败')
      } finally {
        bUltraSaving.value = false
      }
    }

    onMounted(() => { store.fetchBatches(); store.fetchRecords() })

    function formatDate(d: string): string {
      if (!d || d.length !== 8) return d
      return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`
    }
    function formatShortDateTime(dt: string): string {
      if (!dt) return '-'
      // 处理 ISO 格式: 2026-07-08T14:32:15.123456 → 07-08 14:32
      const match = dt.match(/^\d{4}-(\d{2})-(\d{2})[T ](\d{2}:\d{2})/)
      if (match) return `${match[1]}-${match[2]} ${match[3]}`
      // 处理空格分隔: 2026-07-08 14:32:15 → 07-08 14:32
      const parts = dt.split(/[T ]/)
      if (parts.length >= 2) {
        const d = parts[0].split('-')
        const t = parts[1].split(':')
        if (d.length === 3 && t.length >= 2) return `${d[1]}-${d[2]} ${t[0]}:${t[1]}`
      }
      return dt
    }
    function formatFollicles(follicles: BUltraResult['right_follicles'] | BUltraResult['left_follicles']): string {
      if (!follicles || !Array.isArray(follicles) || follicles.length === 0) return '-'
      return follicles.map((f) => `${f.size}×${f.count}`).join('  ')
    }

    // --- ASR (持久化到后端, 多模型管理) ---
    const asrModels = ref<any[]>([])          // 所有 active ASR 模型
    const asrModelId = ref<number | undefined>(undefined)  // 当前选中的 ASR 模型
    const asrRunning = ref(false)
    const asrProgress = ref<{ seg_index: number; total: number } | null>(null)
    const asrPartialSegments = ref<Record<number, string>>({})
    // 当前检查记录的所有 ASR 结果 (按模型分组)
    const asrResultsAll = ref<any[]>([])
    // 当前选中的 ASR 结果 (用于展示 + LLM 输入)
    const selectedAsrResult = ref<any>(null)

    // 辅助: 从同一模型多条历史中选择最优记录
    function pickBestAsrResult(oldResult: any | undefined, newResult: any) {
      if (!oldResult) return newResult

      const rank = (r: any) => {
        if (r.status === 'success' && r.full_transcript) return 3
        if (r.status === 'success') return 2
        if (r.status === 'running') return 1
        if (r.status === 'failed') return 0
        return -1
      }

      const oldRank = rank(oldResult)
      const newRank = rank(newResult)

      if (newRank > oldRank) return newResult
      if (newRank < oldRank) return oldResult

      // 同 rank, 优先 is_current
      if (newResult.is_current && !oldResult.is_current) return newResult
      if (oldResult.is_current && !newResult.is_current) return oldResult

      // 同 rank, 同 is_current, 取 created_at 更新者
      const oldTime = oldResult.created_at ? new Date(oldResult.created_at).getTime() : 0
      const newTime = newResult.created_at ? new Date(newResult.created_at).getTime() : 0
      return newTime >= oldTime ? newResult : oldResult
    }

    // 计算属性: 按 asr_model_id 分组, 每个模型选最优结果
    const asrResultByModelId = computed(() => {
      const map: Record<number, any> = {}
      for (const r of asrResultsAll.value) {
        const modelId = r.asr_model_id
        map[modelId] = pickBestAsrResult(map[modelId], r)
      }
      return map
    })

    // 计算属性: 当前选中模型的转写状态
    const currentAsrStatus = computed(() => {
      if (!asrModelId.value) return 'idle'
      const r = asrResultByModelId.value[asrModelId.value]
      if (!r) return 'idle'
      return r.status  // success / running / failed
    })

    // --- 批量执行：作用于当前筛选出的检查记录 ---
    const batchAsrModelId = ref<number | undefined>(undefined)
    const batchLlmModelId = ref<number | undefined>(undefined)
    const batchTemplateId = ref<number | undefined>(undefined)
    const batchPromptContent = ref('')
    const batchRunning = ref(false)
    const batchMode = ref<'asr' | 'llm' | 'both' | ''>('')
    const batchProgress = reactive({
      total: 0,
      done: 0,
      success: 0,
      failed: 0,
      current: '',
    })
    const batchFailures = ref<{ id: number; record_id: string; date: string; stage: string; error: string }[]>([])

    async function loadModels() {
      try {
        const [asr, llm] = await Promise.all([modelApi.list('asr'), modelApi.list('llm')])
        // 只显示 active 模型
        asrModels.value = (asr as any[]).filter((m: any) => m.status === 'active')
        llmModels.value = (llm as any[]).filter((m: any) => m.status === 'active')
        if (llm.length > 0) {
          llmModelId.value = llm.find((m: any) => m.is_default)?.id || llm[0].id
          batchLlmModelId.value = llm.find((m: any) => m.is_default)?.id || llm[0].id
        }
        // ASR 默认选中第一个 (后续根据当前结果调整)
        if (asrModels.value.length > 0 && !asrModelId.value) {
          asrModelId.value = asrModels.value[0].id
        }
        if (asrModels.value.length > 0 && !batchAsrModelId.value) {
          batchAsrModelId.value = asrModels.value.find((m: any) => m.is_default)?.id || asrModels.value[0].id
        }
      } catch (e) { console.error(e) }
    }

    // 加载当前检查记录的所有 ASR 结果
    async function loadAsrResults() {
      if (!selectedRecord.value) return
      const examRecordId = selectedRecord.value.id  // exam_record_id = patient_records.id
      try {
        const h = await patientApi.listAsrResults(examRecordId)
        asrResultsAll.value = h || []
      } catch { asrResultsAll.value = [] }

      // 自动选择最佳模型
      const map = asrResultByModelId.value
      // 优先 is_current + success
      let bestMid: number | undefined
      for (const mid of Object.keys(map)) {
        const r = map[mid]
        if (r.is_current && r.status === 'success') {
          bestMid = Number(mid)
          break
        }
      }
      // 其次第一个 success
      if (!bestMid) {
        for (const mid of Object.keys(map)) {
          if (map[mid].status === 'success') {
            bestMid = Number(mid)
            break
          }
        }
      }
      // 其次保持当前选择 (如果仍在 active 列表)
      if (!bestMid && asrModelId.value && asrModels.value.find(m => m.id === asrModelId.value)) {
        bestMid = asrModelId.value
      }
      // 否则第一个 active 模型
      if (!bestMid && asrModels.value.length > 0) {
        bestMid = asrModels.value[0].id
      }
      if (bestMid) asrModelId.value = bestMid

      // 更新当前展示结果
      updateSelectedAsrResult()
    }

    // 根据当前选中模型更新展示结果
    function updateSelectedAsrResult() {
      if (!asrModelId.value) {
        selectedAsrResult.value = null
        return
      }
      const r = asrResultByModelId.value[asrModelId.value]
      selectedAsrResult.value = r || null
    }

    async function runAsr() {
      if (!asrModelId.value || !selectedRecord.value) return
      const examRecordId = selectedRecord.value.id
      asrRunning.value = true
      asrProgress.value = null
      asrPartialSegments.value = {}
      try {
        const es = patientApi.runAsrSSE(examRecordId, asrModelId.value)
        es.addEventListener('progress', () => { /* total info */ })
        es.addEventListener('segment', () => {
          // 实时预览由 loadAsrResults 刷新
        })
        es.addEventListener('complete', async () => {
          asrProgress.value = null
          asrRunning.value = false
          es.close()
          // 从后端刷新正式结果
          await loadAsrResults()
        })
        es.addEventListener('error', () => {
          message.error('ASR 失败')
          asrProgress.value = null
          asrRunning.value = false
          es.close()
          // 刷新以显示失败状态
          loadAsrResults()
        })
      } catch (e) {
        message.error('ASR 启动失败')
        asrProgress.value = null
        asrRunning.value = false
      }
    }

    // --- LLM (持久化到后端, 基于当前选中的 ASR 结果) ---
    const llmModels = ref<any[]>([])
    const llmModelId = ref<number | undefined>(undefined)
    const llmRunning = ref(false)
    const currentLlmResult = ref<any>(null)
    const llmHistory = ref<any[]>([])
    const llmTab = ref<'current' | 'history'>('current')
    const llmPrompt = ref(`默认提示词`)

    async function loadCurrentLlmResult() {
      if (!selectedRecord.value) return
      const examRecordId = selectedRecord.value.id
      try {
        const res = await patientApi.getLlmCurrent(examRecordId)
        currentLlmResult.value = res || null
      } catch { currentLlmResult.value = null }
      try {
        const h = await patientApi.listLlmResults(examRecordId)
        llmHistory.value = h || []
      } catch { llmHistory.value = [] }
    }

    async function runLlm() {
      if (!selectedRecord.value) return
      if (!selectedAsrResult.value) {
        message.error('请先完成该检查记录的 ASR 转写')
        return
      }
      if (!llmModelId.value) {
        message.error('请选择 LLM 模型')
        return
      }
      const examRecordId = selectedRecord.value.id
      llmRunning.value = true
      // 调试日志:确认使用哪个模板
      console.log('[LLM] selectedTemplateId=', selectedTemplateId.value)
      console.log('[LLM] prompt_len=', llmPrompt.value.length)
      console.log('[LLM] prompt_has_right_follicles=', llmPrompt.value.includes('right_follicles'))
      console.log('[LLM] llm_model_id=', llmModelId.value)
      try {
        const res = await patientApi.runLlm(examRecordId, {
          llm_model_id: llmModelId.value!,
          asr_result_id: selectedAsrResult.value?.id,
          prompt_content: llmPrompt.value,
          prompt_template_id: selectedTemplateId.value,
        })
        await loadCurrentLlmResult()
        await store.fetchRecords()
        message.success('LLM 提取成功')
      } catch (e: any) {
        message.error(`LLM 提取失败: ${e?.response?.data?.detail || e?.message || ''}`)
      } finally {
        llmRunning.value = false
      }
    }

    // 获取 ASR 模型状态颜色
    function getAsrModelStatusColor(modelId: number): string {
      const r = asrResultByModelId.value[modelId]
      if (!r) return 'default'
      if (r.status === 'success') return 'blue'
      if (r.status === 'running') return 'orange'
      if (r.status === 'failed') return 'red'
      return 'default'
    }

    // 获取 ASR 模型状态文案
    function getAsrModelStatusText(modelId: number): string {
      const r = asrResultByModelId.value[modelId]
      if (!r) return '未转写'
      if (r.status === 'success') return '已完成'
      if (r.status === 'running') return '转写中'
      if (r.status === 'failed') return '失败'
      return '未知'
    }

    // 点击 ASR 模型标签切换展示
    function selectAsrModel(model: any) {
      asrModelId.value = model.id
      const r = asrResultByModelId.value[model.id]
      // 无论 success/failed/running,都应展示记录;只有无结果时才置空
      selectedAsrResult.value = r || null
    }

    // LLM 历史操作
    function viewLlmHistory(record: any) {
      currentLlmResult.value = record
      llmTab.value = 'current'
      message.info(`已查看第 ${record.id} 条 LLM 结果`, 1.5)
    }

    async function setLlmAsCurrent(resultId: number) {
      if (!selectedRecord.value) return
      const examRecordId = selectedRecord.value.id
      try {
        await patientApi.setLlmCurrent(examRecordId, resultId)
        message.success('已设为当前')
        await loadCurrentLlmResult()  // 同时刷新 current + history
        await store.fetchRecords()
      } catch (e: any) {
        message.error(`设置失败: ${e?.response?.data?.detail || e?.message || ''}`)
      }
    }

    function exportCurrentLlmHistory() {
      if (!selectedRecord.value) return
      const url = patientApi.exportLlmResults(selectedRecord.value.id)
      window.open(url, '_blank')
      message.success('正在导出...', 1.5)
    }

    // 清空当前检查记录的 LLM 历史
    async function confirmClearLlmHistory() {
      if (!selectedRecord.value) return
      clearing.value = true
      try {
        const res = await patientApi.clearLlmResults(selectedRecord.value.id)
        message.success(`已清空 ${res?.deleted || 0} 条 LLM 历史`)
        currentLlmResult.value = null
        llmHistory.value = []
        llmTab.value = 'current'
        await store.fetchRecords()
      } catch (e: any) {
        message.error(`清空失败: ${e?.response?.data?.detail || e?.message || ''}`)
      } finally {
        clearing.value = false
        showClearConfirm.value = false
      }
    }

    // ========== 提示词模版 ==========
    const promptTemplates = ref<any[]>([])
    const selectedTemplateId = ref<number | undefined>(undefined)
    const showTemplateModal = ref(false)
    const showLlmDetailModal = ref(false)
    const showClearConfirm = ref(false)
    const clearing = ref(false)
    const templateTab = ref<'edit' | 'preview'>('edit')
    const templateLoading = ref(false)
    const templateSaving = ref(false)
    const templateForm = reactive<{ id?: number; name: string; content: string; is_default: boolean }>({
      name: '',
      content: '',
      is_default: false,
    })

    // Markdown 预览
    const templatePreviewHtml = computed(() => md.render(templateForm.content || ''))

    // LLM 结构化结果兼容
    const structured = computed(() => currentLlmResult.value?.structured || currentLlmResult.value?.structured_result || {})

    // LLM 转写/总结内容 (只用于给人看,不影响结构化字段)
    const llmDisplayText = computed(() => {
      if (!currentLlmResult.value) return ''
      return (
        currentLlmResult.value.summary_text ||
        currentLlmResult.value.structured?.summary ||
        currentLlmResult.value.raw_text ||
        ''
      )
    })

    // Markdown 默认模版 (英文 JSON 键名, 与前端展示一致)
    const DEFAULT_TEMPLATE_CONTENT = `# 角色

你是一名辅助生殖 B 超检查信息结构化专家。

# 任务

请根据以下 ASR 转写文本,提取本次 B 超检查中的结构化字段,并以 JSON 格式返回。

# ASR 转写文本

{transcript}

# 输出要求

请只返回 JSON,不要返回其他任何解释文字。

# JSON 字段说明

- right_follicle_total: 右侧卵泡总数(整数)
- left_follicle_total: 左侧卵泡总数(整数)
- right_follicles: 右侧卵泡列表,每项为 {"size": 数值, "count": 整数}
- left_follicles: 左侧卵泡列表,每项为 {"size": 数值, "count": 整数}
- endometrium_thickness: 内膜厚度(数值,mm)
- endometrium_type: 内膜类型(A/B/C/A-B 等)
- right_ovary_length: 右卵巢长度(数值,mm)
- right_ovary_width: 右卵巢宽度(数值,mm)
- left_ovary_length: 左卵巢长度(数值,mm)
- left_ovary_width: 左卵巢宽度(数值,mm)
- remark: 备注/总结(文本)

# 返回格式示例

\`\`\`json
{
  "right_follicle_total": 10,
  "left_follicle_total": 6,
  "right_follicles": [
    {"size": 17.5, "count": 1},
    {"size": 15.0, "count": 1}
  ],
  "left_follicles": [
    {"size": 14.3, "count": 1}
  ],
  "endometrium_thickness": 11.7,
  "endometrium_type": "A",
  "right_ovary_length": 31,
  "right_ovary_width": 26,
  "left_ovary_length": 28,
  "left_ovary_width": 27,
  "remark": "未见明显异常"
}
\`\`\``

    async function loadTemplates() {
      templateLoading.value = true
      try {
        promptTemplates.value = await promptTemplateApi.list() as unknown as any[]
        if (promptTemplates.value.length === 0) {
          await promptTemplateApi.initDefaults()
          promptTemplates.value = await promptTemplateApi.list() as unknown as any[]
        }
        // 自动选择默认模版或第一条
        const defaultTmpl = promptTemplates.value.find((t: any) => t.is_default)
        const first = promptTemplates.value[0]
        const target = defaultTmpl ?? first
        if (target) {
          selectedTemplateId.value = target.id
          batchTemplateId.value = target.id
          batchPromptContent.value = target.content
          llmPrompt.value = target.content  // 关键修复:同步到 llmPrompt
          loadTemplateToForm(target)
        }
      } catch (e) {
        console.error('加载模版失败', e)
      } finally {
        templateLoading.value = false
      }
    }

    // 点击左侧模版,加载到右侧表单 + 同步到 llmPrompt
    function selectTemplate(id: number) {
      selectedTemplateId.value = id
      const tmpl = promptTemplates.value.find((t: any) => t.id === id)
      if (tmpl) {
        batchTemplateId.value = tmpl.id
        batchPromptContent.value = tmpl.content
        llmPrompt.value = tmpl.content  // 关键修复
        loadTemplateToForm(tmpl)
      }
    }

    function onBatchTemplateChange(id: number | undefined) {
      batchTemplateId.value = id
      const tmpl = promptTemplates.value.find((t: any) => t.id === id)
      batchPromptContent.value = tmpl?.content || ''
    }

    function waitForAsrComplete(record: PatientExamination, modelId: number): Promise<void> {
      return new Promise((resolve, reject) => {
        const es = patientApi.runAsrSSE(record.id, modelId)
        let settled = false
        const timeout = window.setTimeout(() => {
          if (settled) return
          settled = true
          es.close()
          reject(new Error('ASR 超时'))
        }, 10 * 60 * 1000)

        const finish = () => {
          if (settled) return
          settled = true
          window.clearTimeout(timeout)
          es.close()
          resolve()
        }

        const fail = (event?: any) => {
          if (settled) return
          settled = true
          window.clearTimeout(timeout)
          es.close()
          const detail = event?.data ? String(event.data) : ''
          reject(new Error(detail || 'ASR 失败'))
        }

        es.addEventListener('complete', finish)
        es.addEventListener('error', fail)
      })
    }

    async function getCurrentAsrForRecord(record: PatientExamination) {
      const current = await patientApi.getAsrCurrent(record.id)
      return current as any
    }

    async function waitForLatestAsrVisible(record: PatientExamination) {
      await new Promise((resolve) => window.setTimeout(resolve, 300))
      return getCurrentAsrForRecord(record)
    }

    async function getOrReuseAsrForRecord(record: PatientExamination, modelId: number) {
      // 查询指定 modelId 的已有成功结果
      const results = await patientApi.listAsrResults(record.id)
      const list = Array.isArray(results) ? results : (results?.data || [])
      const candidates = list
        .filter((r: any) => r.asr_model_id === modelId && r.status === 'success' && r.full_transcript)
        .sort((a: any, b: any) => {
          const ta = a.updated_at || a.created_at || ''
          const tb = b.updated_at || b.created_at || ''
          return tb.localeCompare(ta)
        })
      if (candidates.length > 0) {
        return candidates[0] as any
      }
      return null
    }

    async function runLlmForRecord(record: PatientExamination) {
      if (!batchLlmModelId.value) throw new Error('未选择 LLM 模型')
      if (!batchPromptContent.value) throw new Error('未选择提示词模板')

      let asrResultId: number | undefined
      if (batchAsrModelId.value) {
        // 批量模式：使用选定的 ASR 模型
        const reused = await getOrReuseAsrForRecord(record, batchAsrModelId.value)
        if (reused) {
          asrResultId = reused.id
        } else {
          // 没有可复用结果，调用 ASR
          await waitForAsrComplete(record, batchAsrModelId.value)
          await waitForLatestAsrVisible(record)
          const newAsr = await getOrReuseAsrForRecord(record, batchAsrModelId.value)
          if (!newAsr?.id) throw new Error('ASR 执行失败，无可用结果')
          asrResultId = newAsr.id
        }
      } else {
        // 非批量模式：使用当前 ASR
        const asr = await getCurrentAsrForRecord(record)
        if (!asr?.id) throw new Error('该检查记录没有可复用的 ASR 转写结果')
        asrResultId = asr.id
      }

      await patientApi.runLlm(record.id, {
        llm_model_id: batchLlmModelId.value,
        asr_result_id: asrResultId,
        prompt_content: batchPromptContent.value,
        prompt_template_id: batchTemplateId.value,
      })
      return asrResultId
    }

    async function runBatch(mode: 'asr' | 'llm' | 'both') {
      const targets = filteredRecords.value.slice()
      if (!targets.length) {
        message.warning('当前筛选范围内没有检查记录')
        return
      }
      if ((mode === 'asr' || mode === 'both') && !batchAsrModelId.value) {
        message.error('请选择 ASR 模型')
        return
      }
      if ((mode === 'llm' || mode === 'both') && (!batchLlmModelId.value || !batchTemplateId.value)) {
        message.error('请选择 LLM 模型和提示词模板')
        return
      }
      // 启动时为所有目标预校验 LLM 配置，避免每条都 401
      if (mode === 'llm' || mode === 'both') {
        // 前端快速校验模型配置
        const llm = llmModels.value.find((m: any) => m.id === batchLlmModelId.value)
        if (!llm) {
          message.error('所选 LLM 模型不存在')
          return
        }
        if (llm.status !== 'active') {
          message.error(`${llm.name} 未激活，请先在「模型配置」中启用`)
          return
        }
        const missing: string[] = []
        if (!llm.api_key) missing.push('API Key')
        if (!llm.model_name) missing.push('model_name')
        if (!llm.endpoint) missing.push('endpoint')
        if (missing.length) {
          message.error(`${llm.name} 配置不完整，缺少: ${missing.join(', ')}。请先在「模型配置」中补全信息。`)
          return
        }
      }
      if (targets.length > 20 && !window.confirm(`将对当前筛选的 ${targets.length} 条检查记录执行批量任务，确认继续？`)) {
        return
      }

      batchRunning.value = true
      batchMode.value = mode
      batchProgress.total = targets.length
      batchProgress.done = 0
      batchProgress.success = 0
      batchProgress.failed = 0
      batchProgress.current = ''
      batchFailures.value = []

      for (const record of targets) {
        batchProgress.current = `${record.record_id} ${formatDate(record.date)}`
        let stage = 'ASR'
        try {
          if (mode === 'asr' || mode === 'both') {
            stage = 'ASR'
            const existing = batchAsrModelId.value
              ? await getOrReuseAsrForRecord(record, batchAsrModelId.value)
              : null
            if (!existing) {
              await waitForAsrComplete(record, batchAsrModelId.value!)
              await waitForLatestAsrVisible(record)
            }
          }
          if (mode === 'llm' || mode === 'both') {
            stage = 'LLM'
            await runLlmForRecord(record)
          }
          batchProgress.success += 1
        } catch (e: any) {
          console.error('[batch run failed]', record.id, record.record_id, stage, e)
          batchProgress.failed += 1
          batchFailures.value.push({
            id: record.id,
            record_id: record.record_id,
            date: record.date,
            stage,
            error: e?.response?.data?.detail || e?.message || String(e),
          })
        } finally {
          batchProgress.done += 1
        }
      }

      await store.fetchRecords()
      if (drawerOpen.value && selectedRecord.value) {
        await loadAsrResults()
        await loadCurrentLlmResult()
      }
      batchRunning.value = false
      batchMode.value = ''
      batchProgress.current = ''
      if (batchProgress.failed) {
        message.warning(`批量执行完成：成功 ${batchProgress.success} 条，失败 ${batchProgress.failed} 条`)
      } else {
        message.success(`批量执行完成：成功 ${batchProgress.success} 条`)
      }
    }

    function loadTemplateToForm(record: any) {
      templateForm.id = record.id
      templateForm.name = record.name
      templateForm.content = record.content
      templateForm.is_default = record.is_default
    }

    function onTemplateChange(id: number | undefined) {
      if (!id) return
      const tmpl = promptTemplates.value.find((t: any) => t.id === id)
      if (tmpl) {
        llmPrompt.value = tmpl.content
        // 提示用户重新提取
        if (currentLlmResult.value && !llmRunning.value) {
          message.info('提示词已切换,请重新点击"开始提取"', 2)
        }
      }
    }

    function createNewTemplate() {
      templateForm.id = undefined
      templateForm.name = ''
      templateForm.content = DEFAULT_TEMPLATE_CONTENT
      templateForm.is_default = false
      selectedTemplateId.value = undefined
      templateTab.value = 'edit'
    }

    function resetTemplateForm() {
      if (templateForm.id) {
        const tmpl = promptTemplates.value.find((t: any) => t.id === templateForm.id)
        if (tmpl) loadTemplateToForm(tmpl)
      } else {
        createNewTemplate()
      }
    }

    // 应用到当前检查
    function applyTemplateToCurrent() {
      if (!templateForm.content?.trim()) {
        message.error('模版内容为空')
        return
      }
      llmPrompt.value = templateForm.content
      if (templateForm.id) selectedTemplateId.value = templateForm.id
      message.success('已应用到当前检查')
    }

    async function saveTemplate() {
      if (!templateForm.name?.trim() || !templateForm.content?.trim()) {
        message.error('请填写模版名称和内容')
        return
      }
      if (!templateForm.content.includes('{transcript}')) {
        message.error('模版内容必须包含 {transcript} 占位符')
        return
      }
      templateSaving.value = true
      try {
        if (templateForm.id) {
          await promptTemplateApi.update(templateForm.id, {
            name: templateForm.name,
            content: templateForm.content,
            is_default: templateForm.is_default,
          })
          message.success('更新成功')
        } else {
          const created = await promptTemplateApi.create({
            name: templateForm.name,
            content: templateForm.content,
            is_default: templateForm.is_default,
          })
          templateForm.id = created?.id
          message.success('创建成功')
        }
        await loadTemplates()
        // 保持当前编辑项选中
        if (templateForm.id) selectedTemplateId.value = templateForm.id
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '保存失败')
      } finally {
        templateSaving.value = false
      }
    }

    async function deleteTemplate(id: number | undefined) {
      if (!id) {
        message.error('请先选择模版')
        return
      }
      try {
        await promptTemplateApi.delete(id)
        message.success('删除成功')
        await loadTemplates()
        // 如果删除的是当前表单模版,重置表单
        if (templateForm.id === id) {
          createNewTemplate()
        }
      } catch {
        message.error('删除失败')
      }
    }

    function compareField(field: string, correct: boolean): boolean {
      if (!normalizedLlmStructured.value || !selectedRecord.value?.result) return false
      const llmVal = (normalizedLlmStructured.value as any)[field]
      const gtVal = (selectedRecord.value.result as any)[field]
      if (llmVal == null || gtVal == null) return false
      const match = String(llmVal).trim() === String(gtVal).trim()
      return correct ? match : !match && llmVal !== undefined
    }

    function formatRawJson(llmResult: any): string {
      if (!llmResult) return ''
      const { model_name, structured, raw_text, accuracy } = llmResult
      const display: any = { model_name, accuracy, structured }
      if (raw_text) display.raw_text = raw_text
      return JSON.stringify(display, null, 2)
    }

    // ======= 卵泡逐项对比 =======
    const normalizedLlmStructured = computed(() => normalizeStructured(currentLlmResult.value?.structured || currentLlmResult.value?.structured_result))

    const rightFollCompare = computed(() => compareFolls(normalizedLlmStructured.value?.right_follicles, selectedRecord.value?.result?.right_follicles))
    const leftFollCompare = computed(() => compareFolls(normalizedLlmStructured.value?.left_follicles, selectedRecord.value?.result?.left_follicles))

    const rightGtFolls = computed(() => {
      return normalizeFollicles(selectedRecord.value?.result?.right_follicles)
    })
    const leftGtFolls = computed(() => {
      return normalizeFollicles(selectedRecord.value?.result?.left_follicles)
    })

    function gtFollClass(size: string | number, side: 'right' | 'left', count?: number): string {
      const llmList = side === 'right'
        ? (normalizedLlmStructured.value?.right_follicles || [])
        : (normalizedLlmStructured.value?.left_follicles || [])
      const normalizedSize = normalizeSize(size)
      const normalizedCount = Number(count || 1)
      const found = llmList.find((f: any) => normalizeSize(f.size) === normalizedSize && Number(f.count || 1) === normalizedCount)
      return found ? 'status-match' : 'status-mismatch'
    }

    function compareFolls(llmFolls: any, gtFolls: any): { size: string; count: number; status: string }[] {
      const result: { size: string; count: number; status: string }[] = []
      const llmList = normalizeFollicles(llmFolls)
      const gtList = normalizeFollicles(gtFolls)

      for (const f of llmList) {
        const s = normalizeSize(f.size)
        const c = Number(f.count || 1)
        const gtMatch = gtList.find((g: any) => normalizeSize(g.size) === s && Number(g.count || 1) === c)
        result.push({ size: s, count: c, status: gtMatch ? 'match' : 'mismatch' })
      }

      for (const f of gtList) {
        const s = normalizeSize(f.size)
        const c = Number(f.count || 1)
        const llmMatch = llmList.find((l: any) => normalizeSize(l.size) === s && Number(l.count || 1) === c)
        if (!llmMatch && !result.find((r) => r.size === s)) {
          result.push({ size: s, count: c, status: 'missing' })
        }
      }

      return result
    }

    function normalizeSize(size: any): string {
      const n = Number(size)
      if (Number.isFinite(n)) return String(Math.round(n * 10) / 10)
      return String(size ?? '').trim()
    }

    function normalizeFollicles(follicles: any): { size: string; count: number }[] {
      if (!Array.isArray(follicles)) return []
      const merged = new Map<string, number>()
      for (const f of follicles) {
        const size = normalizeSize(f?.size)
        if (!size) continue
        const count = Number(f?.count || 1)
        if (!Number.isFinite(count) || count <= 0) continue
        merged.set(size, (merged.get(size) || 0) + count)
      }
      return Array.from(merged.entries())
        .map(([size, count]) => ({ size, count }))
        .sort((a, b) => Number(b.size) - Number(a.size))
    }

    function normalizeStructured(structured: any): any {
      if (!structured || typeof structured !== 'object') return null
      const next = { ...structured }
      const right = normalizeFollicles(next.right_follicles)
      const left = normalizeFollicles(next.left_follicles)
      next.right_follicles = right
      next.left_follicles = left
      if (right.length) next.right_follicle_total = right.reduce((sum, f) => sum + f.count, 0)
      if (left.length) next.left_follicle_total = left.reduce((sum, f) => sum + f.count, 0)
      return next
    }

    // 监听 drawer 中检查记录切换, 自动加载持久化结果 + 自动选中最佳模型
    watch(selectedRecord, async (rec) => {
      selectedAsrResult.value = null
      currentLlmResult.value = null
      asrResultsAll.value = []
      llmHistory.value = []
      llmModelId.value = undefined
      if (rec && drawerOpen.value) {
        await loadAsrResults()
        await loadCurrentLlmResult()
      }
    })

    // 监听 ASR 模型切换, 更新展示结果
    watch(asrModelId, () => {
      updateSelectedAsrResult()
    })

    onMounted(() => {
      loadModels()
      loadTemplates()
      store.fetchBatches()
      store.fetchRecords()
    })

    return {
      searchText, drawerOpen, selectedRecord, batches, selectedBatch, loadingTree,
      allRecords, filteredRecords,
      asrModels, asrModelId, asrRunning, asrProgress, runAsr,
      asrResultByModelId, currentAsrStatus, selectedAsrResult,
      llmModels, llmModelId, llmRunning, llmResult: currentLlmResult, llmPrompt, runLlm, compareField, formatRawJson,
      structured, llmDisplayText,
      selectBatch, openDetail, closeDrawer, onRowClick, formatDate, formatShortDateTime, formatFollicles,
      getLlmStatusColor, getLlmStatusText, formatAccuracy, getMatchStatus, matchTagColor, matchTagText,
      getListAsrStatusColor, getListAsrStatusText,
      getAsrModelStatusColor, getAsrModelStatusText, selectAsrModel,
      ScanOutlined, RobotOutlined, CheckCircleOutlined, CloseCircleOutlined, SettingOutlined, PlusOutlined, EyeOutlined, EditOutlined,
      promptTemplates, selectedTemplateId, showTemplateModal, showLlmDetailModal, templateTab, llmTab,
      batchAsrModelId, batchLlmModelId, batchTemplateId, batchRunning, batchMode, batchProgress, batchFailures, onBatchTemplateChange, runBatch,
      templateLoading, templateSaving, templateForm, templatePreviewHtml, showClearConfirm, clearing,
      onTemplateChange, selectTemplate, createNewTemplate, viewLlmHistory, setLlmAsCurrent, exportCurrentLlmHistory, confirmClearLlmHistory, applyTemplateToCurrent, resetTemplateForm, saveTemplate, deleteTemplate,
      asrResultsAll, llmHistory,
      // 卵泡逐项对比
      normalizedLlmStructured, rightFollCompare, leftFollCompare, rightGtFolls, leftGtFolls, gtFollClass,
      // 真实 B 超结果编辑
      showBUltraModal, bUltraSaving, bUltraForm, openEditBUltra,
    }
  },
})
</script>

<style scoped>
.follicle-list { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.follicle-item {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  background: #f5f5f5;
  border: 1px solid #d9d9d9;
}
.follicle-item.status-match {
  color: #52c41a;
  background: #f6ffed;
  border-color: #b7eb8f;
}
.follicle-item.status-mismatch {
  color: #ff4d4f;
  background: #fff2f0;
  border-color: #ffccc7;
}
.follicle-item.status-missing {
  color: #ff4d4f;
  background: #fff2f0;
  border-color: #ffccc7;
  text-decoration: line-through;
}
.markdown-preview {
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 16px;
  min-height: 420px;
  max-height: 520px;
  overflow: auto;
  background: #fff;
  font-size: 13px;
  line-height: 1.7;
}
.markdown-preview h1 { font-size: 18px; font-weight: 600; margin: 16px 0 8px; border-bottom: 1px solid #eee; padding-bottom: 6px; }
.markdown-preview h2 { font-size: 16px; font-weight: 600; margin: 14px 0 8px; }
.markdown-preview h3 { font-size: 14px; font-weight: 600; margin: 12px 0 6px; }
.markdown-preview p { margin: 6px 0; }
.markdown-preview ul, .markdown-preview ol { padding-left: 24px; margin: 6px 0; }
.markdown-preview li { margin: 3px 0; }
.markdown-preview pre { background: #f6f8fa; padding: 12px; border-radius: 6px; overflow-x: auto; margin: 8px 0; }
.markdown-preview code { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 12px; background: rgba(175,184,193,0.2); padding: 2px 4px; border-radius: 4px; }
.markdown-preview pre code { background: transparent; padding: 0; }
.markdown-preview blockquote { border-left: 4px solid #ddd; margin: 8px 0; padding: 4px 12px; color: #666; }
.llm-summary-box {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 6px;
  max-height: 400px;
  overflow-y: auto;
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.7;
  color: #333;
}
.table-ellipsis {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
</style>
