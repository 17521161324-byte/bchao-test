<template>
  <div class="page-container">
    <!-- 筛选区域 -->
    <a-card style="margin-bottom: 16px">
      <div class="filter-row">
        <div class="batch-filter">
          <a-space wrap>
            <span style="color: #666">批次：</span>
            <a-checkable-tag :checked="selectedBatch === null" @click="selectBatch(null)" style="cursor: pointer">全部</a-checkable-tag>
            <a-checkable-tag v-for="batch in batches" :key="batch.date" :checked="selectedBatch === batch.date" @click="selectBatch(batch.date)" style="cursor: pointer">
              {{ formatDate(batch.date) }} ({{ batch.patient_count }}人)
            </a-checkable-tag>
          </a-space>
        </div>
        <a-input-search v-model:value="searchText" class="record-search" placeholder="搜索病历号" allow-clear />
      </div>
    </a-card>

    <!-- 批量执行区域 -->
    <a-card size="small" title="批量执行" style="margin-bottom: 16px">
      <div class="batch-action-row">
        <div class="batch-select">
          <a-select v-model:value="batchAsrModelId" placeholder="选择 ASR 模型" allow-clear style="width: 100%">
            <a-select-option v-for="m in asrModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
          </a-select>
        </div>
        <div class="batch-select">
          <a-select v-model:value="batchTemplateId" placeholder="选择提示词模板" allow-clear style="width: 100%" @change="onBatchTemplateChange">
            <a-select-option v-for="t in promptTemplates" :key="t.id" :value="t.id">{{ t.name }}</a-select-option>
          </a-select>
        </div>
        <div class="batch-select">
          <a-select v-model:value="batchLlmModelId" placeholder="选择 LLM 模型" allow-clear style="width: 100%">
            <a-select-option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
          </a-select>
        </div>
        <div class="batch-buttons">
          <a-space wrap>
            <a-button type="primary" :disabled="!batchAsrModelId || batchRunning" :loading="batchRunning && batchMode === 'asr'" @click="runBatch('asr')">批量 ASR</a-button>
            <a-button :disabled="!batchLlmModelId || !batchTemplateId || batchRunning" :loading="batchRunning && batchMode === 'llm'" @click="runBatch('llm')">批量 LLM</a-button>
            <a-button type="primary" ghost :disabled="!batchAsrModelId || !batchLlmModelId || !batchTemplateId || batchRunning" :loading="batchRunning && batchMode === 'both'" @click="runBatch('both')">ASR + LLM</a-button>
            <span style="font-size: 12px; color: #666">作用范围：当前筛选 {{ filteredRecords.length }} 条</span>
          </a-space>
        </div>
      </div>
      <div v-if="batchRunning || batchFailures.length" style="margin-top: 12px">
        <div v-if="batchRunning" style="color: #666; font-size: 12px; margin-bottom: 8px">
          执行中：{{ batchProgress.done }}/{{ batchProgress.total }}
          成功 {{ batchProgress.success }} 条，失败 {{ batchProgress.failed }} 条
          <span v-if="batchProgress.current">，当前：{{ batchProgress.current }}</span>
          <span v-if="batchProgress.stage">，阶段：{{ batchProgress.stage }}</span>
          <span v-if="batchProgress.asrTotal">，ASR 分段：{{ batchProgress.asrDone }}/{{ batchProgress.asrTotal }}</span>
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
      <div class="table-toolbar">
        <a-space wrap>
          <span class="toolbar-label">准确率口径：</span>
          <a-radio-group v-model:value="accuracyMode" size="small" button-style="solid">
            <a-radio-button value="without_remark">不含备注</a-radio-button>
            <a-radio-button value="with_remark">含备注</a-radio-button>
          </a-radio-group>
          <a-button size="small" type="primary" ghost :disabled="!filteredRecords.length" @click="exportLatestLlmForFilteredRecords">
            导出当前最新结果
          </a-button>
          <span style="font-size: 12px; color: #666">导出范围：当前筛选 {{ filteredRecords.length }} 条</span>
        </a-space>
      </div>
      <div class="field-stats-row">
        <span class="toolbar-label">字段成功率：</span>
        <a-tag v-for="stat in fieldMatchStats" :key="stat.key" :color="stat.rate >= 0.9 ? 'green' : stat.rate >= 0.7 ? 'orange' : 'red'">
          {{ stat.label }} {{ stat.matched }}/{{ stat.total }} · {{ stat.total ? (stat.rate * 100).toFixed(1) : '-' }}%
        </a-tag>
        <span class="toolbar-label" style="margin-left: 12px">卵泡平均正确率：</span>
        <a-tag v-for="stat in follicleAverageStats" :key="stat.key" :color="stat.average >= 0.9 ? 'green' : stat.average >= 0.7 ? 'orange' : 'red'">
          {{ stat.label }} {{ stat.total ? (stat.average * 100).toFixed(1) : '-' }}%（n={{ stat.total }}）
        </a-tag>
      </div>
      <a-tabs class="data-tabs">
        <a-tab-pane key="records" tab="检查记录">
      <a-table :data-source="filteredRecords" :loading="loadingTree" :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }" size="small" row-key="id" :columns="resizableColumns">
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'record_id'">{{ record.record_id }}</template>
          <template v-else-if="column.dataIndex === 'date'">{{ formatDate(record.date) }}</template>
          <template v-else-if="column.dataIndex === 'note'">
            <a-tooltip :title="record.note || '-'">
              <span class="table-ellipsis">{{ record.note || '-' }}</span>
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'has_audio'">
            <a-tag v-if="record.has_audio" color="green">有 ({{ record.segs?.length || 0 }}段)</a-tag>
            <a-tag v-else color="red">无</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'has_result'">
            <a-tag v-if="record.has_result" color="green">有</a-tag>
            <a-tag v-else color="default">无</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'asr_status'">
            <a-tag :color="getListAsrStatusColor(record)">{{ getListAsrStatusText(record) }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'llm_status'">
            <a-tag v-if="!record.latest_llm || record.latest_llm.status !== 'success'" :color="getLlmStatusColor(record)">{{ getLlmStatusText(record) }}</a-tag>
            <div v-if="record.latest_llm" class="llm-model-info">
              <span class="llm-model-prompt">{{ record.latest_llm.prompt_template_name || getPromptTemplateNameById(record.latest_llm.prompt_template_id) || (record.latest_llm.status === 'success' ? '已提取' : '-') }}</span>
            </div>
            <div v-else-if="record.latest_asr" class="llm-model-info">
              <span class="muted">-</span>
            </div>
          </template>
          <template v-else-if="column.dataIndex === 'accuracy'">{{ formatAccuracy(getAccuracyValue(record)) }}</template>
          <template v-else-if="getFollicleRateColumn(column.dataIndex)">
            <a-tag
              :color="follicleRateTagColor(record, getFollicleRateColumn(column.dataIndex)?.group || '')"
              class="match-tag-sm clickable"
              @click.stop="openFieldCompare(record, getFollicleRateColumn(column.dataIndex)?.group || '')"
              :title="`${getFollicleRateColumn(column.dataIndex)?.label}: 点击查看专项对比`"
            >
              {{ follicleRateDisplayText(record, getFollicleRateColumn(column.dataIndex)?.group || '') }}
            </a-tag>
          </template>
          <template v-else-if="getFieldColumn(column.dataIndex)">
            <a-tag :color="fieldStatusTagColor(record, getFieldColumn(column.dataIndex)?.group || '')" class="match-tag-sm clickable field-status-tag" @click.stop="openFieldCompare(record, getFieldColumn(column.dataIndex)?.group || '')" :title="`${getFieldColumn(column.dataIndex)?.label}: 点击查看专项对比`">
              <div v-if="isFollicleGroup(getFieldColumn(column.dataIndex)?.group || '')" class="follicle-summary-cell">
                <div class="follicle-summary-main">{{ fieldStatusDisplayText(record, getFieldColumn(column.dataIndex)?.group || '') }}</div>
                <div v-for="line in follicleMismatchLines(record, getFieldColumn(column.dataIndex)?.group || '')" :key="line" class="follicle-summary-line">
                  {{ line }}
                </div>
              </div>
              <template v-else>{{ fieldStatusDisplayText(record, getFieldColumn(column.dataIndex)?.group || '') }}</template>
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'action'">
            <a-button size="small" type="link" @click.stop="openDetail(record)">详情</a-button>
          </template>
        </template>
      </a-table>
        </a-tab-pane>

        <a-tab-pane key="attribution" tab="逐字段归因">
          <div class="attribution-stats">
            <a-card size="small" class="attribution-stat-card">
              <div class="stat-label">总字段数</div>
              <div class="stat-value">{{ attributionOverallStats.total }}</div>
            </a-card>
            <a-card size="small" class="attribution-stat-card">
              <div class="stat-label">正确率</div>
              <div class="stat-value success">{{ (attributionOverallStats.accuracy * 100).toFixed(1) }}%</div>
              <div class="stat-sub">正确 {{ attributionOverallStats.correct }} / 分母 {{ attributionOverallStats.denominator }}</div>
            </a-card>
            <a-card size="small" class="attribution-stat-card">
              <div class="stat-label">错误/异常</div>
              <div class="stat-value danger">{{ attributionOverallStats.error + attributionOverallStats.abnormal }}</div>
              <div class="stat-sub">错误 {{ attributionOverallStats.error }}，异常 {{ attributionOverallStats.abnormal }}</div>
            </a-card>
            <a-card size="small" class="attribution-stat-card">
              <div class="stat-label">排除/未提取</div>
              <div class="stat-value warning">{{ attributionOverallStats.excluded + attributionOverallStats.missing }}</div>
              <div class="stat-sub">排除 {{ attributionOverallStats.excluded }}，未提取 {{ attributionOverallStats.missing }}</div>
            </a-card>
          </div>

          <div class="field-attribution-stats">
            <a-tag v-for="stat in attributionFieldStats" :key="stat.key" :color="stat.accuracy >= 0.9 ? 'green' : stat.accuracy >= 0.7 ? 'orange' : 'red'">
              {{ stat.label }}：{{ (stat.accuracy * 100).toFixed(1) }}%（对{{ stat.correct }}/错{{ stat.error }}/异{{ stat.abnormal }}/排{{ stat.excluded }}/缺{{ stat.missing }}）
            </a-tag>
          </div>

          <div class="attribution-filters">
            <a-input-search v-model:value="attributionKeyword" placeholder="搜索病历号" allow-clear style="width: 180px" />
            <a-select v-model:value="attributionFieldFilter" placeholder="字段" allow-clear style="width: 150px">
              <a-select-option v-for="field in fieldColumns" :key="field.group" :value="field.group">{{ field.label }}</a-select-option>
            </a-select>
            <a-select v-model:value="attributionStatusFilter" placeholder="状态" allow-clear style="width: 130px">
              <a-select-option value="正确">正确</a-select-option>
              <a-select-option value="错误">错误</a-select-option>
              <a-select-option value="排除">排除</a-select-option>
              <a-select-option value="异常">异常</a-select-option>
              <a-select-option value="未提取">未提取</a-select-option>
            </a-select>
            <a-select v-model:value="attributionLevelFilter" placeholder="归因层级" allow-clear style="width: 150px">
              <a-select-option v-for="level in attributionLevelOptions" :key="level" :value="level">{{ level }}</a-select-option>
            </a-select>
            <a-select v-model:value="attributionErrorTypeFilter" placeholder="错误类型" allow-clear style="width: 180px">
              <a-select-option v-for="type in attributionErrorTypeOptions" :key="type" :value="type">{{ type }}</a-select-option>
            </a-select>
            <a-checkbox v-model:checked="attributionOnlyMarked">只看人工标记</a-checkbox>
            <a-checkbox v-model:checked="attributionOnlyFollicle">只看卵泡字段</a-checkbox>
          </div>

          <a-table
            :data-source="filteredFieldAttributionRows"
            :columns="fieldAttributionColumns"
            :pagination="{ pageSize: 30, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }"
            size="small"
            row-key="key"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.dataIndex === 'status'">
                <a-tag :color="record.status === '正确' ? 'green' : record.status === '排除' ? 'orange' : record.status === '未提取' ? 'default' : 'red'">{{ record.status }}</a-tag>
              </template>
              <template v-else-if="column.dataIndex === 'original_judgement'">
                <span class="attribution-original">{{ record.original_judgement }}</span>
              </template>
            </template>
          </a-table>
        </a-tab-pane>
      </a-tabs>
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
          <a-descriptions-item label="最新ASR">{{ selectedAsrResult?.model_name || selectedAsrResult?.asr_model_name || selectedRecord.latest_asr?.asr_model_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="最新LLM">{{ selectedRecord.latest_llm?.llm_model_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="提示词">{{ selectedRecord.latest_llm?.prompt_template_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="最新准确率">{{ formatAccuracy(getAccuracyValue(selectedRecord)) }}</a-descriptions-item>
        </a-descriptions>

        <a-card size="small" style="margin-bottom: 16px">
          <template #title><span style="font-size: 12px">检查备注 / 人工标注</span></template>
          <a-space direction="vertical" style="width: 100%">
            <a-textarea
              v-model:value="recordNoteDraft"
              :rows="2"
              placeholder="可记录该检查的特殊情况、错误原因、人工判断等；不参与真实 B 超结果和准确率计算"
            />
            <div style="text-align: right">
              <a-button size="small" type="primary" :loading="recordNoteSaving" @click="saveRecordNote">保存备注</a-button>
            </div>
          </a-space>
        </a-card>

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
                    <span :style="{ color: detailGroupTextColor('right_ovary') }">
                      {{ llmResult.structured?.right_ovary_length && llmResult.structured?.right_ovary_width ? `${llmResult.structured.right_ovary_length} × ${llmResult.structured.right_ovary_width} mm` : '-' }}
                    </span>
                  </a-descriptions-item>
                  <a-descriptions-item label="左卵巢">
                    <span :style="{ color: detailGroupTextColor('left_ovary') }">
                      {{ llmResult.structured?.left_ovary_length && llmResult.structured?.left_ovary_width ? `${llmResult.structured.left_ovary_length} × ${llmResult.structured.left_ovary_width} mm` : '-' }}
                    </span>
                  </a-descriptions-item>
                  <a-descriptions-item label="备注" :span="2">
                    <div class="remark-text">{{ llmResult.structured?.remark || '-' }}</div>
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
                <a-descriptions-item label="备注" :span="2">
                  <div class="remark-text">{{ selectedRecord.result.remark || '-' }}</div>
                </a-descriptions-item>
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
          <a-col :span="12">
            <a-form-item label="右侧卵泡总数">
              <a-input-number v-model:value="bUltraForm.right_follicle_total" style="width: 100%" placeholder="自动求和" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="左侧卵泡总数">
              <a-input-number v-model:value="bUltraForm.left_follicle_total" style="width: 100%" placeholder="自动求和" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-alert
          type="info"
          show-icon
          style="margin-bottom: 12px"
          message="卵泡明细支持 10x2、10×2、10*2、10；可用逗号、顿号、分号、空格或换行分隔，省略数量时按 1 个保存。"
        />
        <a-form-item label="右侧卵泡明细"><a-textarea v-model:value="bUltraForm.right_follicles_raw" :rows="3" placeholder="10x2&#10;12×1&#10;13.5" /></a-form-item>
        <a-form-item label="左侧卵泡明细"><a-textarea v-model:value="bUltraForm.left_follicles_raw" :rows="3" placeholder="10x1，12×2，13.5" /></a-form-item>
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

    <!-- 字段专项对比弹窗 -->
    <a-modal
      v-model:open="compareModalOpen"
      :title="`${compareModalRecord?.record_id || ''} - ${compareModalGroupTitle}`"
      width="700px"
      :footer="null"
      @cancel="compareModalOpen = false"
      destroy-on-close
    >
      <template v-if="compareModalRecord">
        <!-- 顶部基础信息 -->
        <a-descriptions :column="2" bordered size="small" style="margin-bottom: 12px">
          <a-descriptions-item label="病历号">{{ compareModalRecord.record_id }}</a-descriptions-item>
          <a-descriptions-item label="日期">{{ formatDate(compareModalRecord.date) }}</a-descriptions-item>
          <a-descriptions-item label="准确率">{{ formatAccuracy(getAccuracyValue(compareModalRecord)) }}</a-descriptions-item>
          <a-descriptions-item label="ASR模型">{{ compareModalRecord.latest_llm?.asr_model_name || compareModalRecord.latest_asr?.asr_model_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="LLM模型">{{ compareModalRecord.latest_llm?.llm_model_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="提示词">{{ compareModalRecord.latest_llm?.prompt_template_name || '-' }}</a-descriptions-item>
        </a-descriptions>

        <!-- ASR 摘要 -->
        <a-card size="small" style="margin-bottom: 12px">
          <template #title>
            <span>ASR 转写（前 500 字）</span>
          </template>
          <div v-if="compareModalRecord.latest_llm?.full_transcript" class="text-box small">{{ compareModalRecord.latest_llm.full_transcript.substring(0, 500) }}</div>
          <div v-else-if="compareModalRecord.latest_llm?.asr_transcript" class="text-box small">{{ compareModalRecord.latest_llm.asr_transcript.substring(0, 500) }}</div>
          <div v-else class="muted" style="padding: 8px">当前列表数据未包含 ASR 全文，请进入检查详情查看完整转写</div>
        </a-card>

        <!-- 字段对比表 -->
        <a-table
          :data-source="getFieldCompareRows(compareModalRecord, compareModalGroupKey)"
          size="small"
          row-key="field"
          :pagination="false"
          bordered
        >
          <a-table-column title="字段" data-index="label" :width="120" />
          <a-table-column title="匹配" :width="80" align="center">
            <template #default="{ record }">
              <a-tag v-if="record.match === 'match'" color="green">✓</a-tag>
              <a-tag v-else-if="record.match === 'mismatch'" color="red">✗</a-tag>
              <a-tag v-else-if="record.match === 'ignored'" color="orange">⚠</a-tag>
              <a-tag v-else color="default">-</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="LLM结果" data-index="llmValue">
            <template #default="{ record }"><div class="compare-value-cell">{{ record.llmValue }}</div></template>
          </a-table-column>
          <a-table-column title="真实值" data-index="gtValue">
            <template #default="{ record }"><div class="compare-value-cell">{{ record.gtValue }}</div></template>
          </a-table-column>
        </a-table>

        <!-- 人工标记区域 -->
        <a-divider style="margin-top: 16px">人工标记</a-divider>
        <div :key="compareModalMarkRefreshKey">
          <template v-if="getFieldReviewMark(compareModalRecord, compareModalGroupKey)">
            <a-alert :type="getFieldReviewMark(compareModalRecord, compareModalGroupKey)?.mark_type === 'exclude' ? 'warning' : 'error'" show-icon style="margin-bottom: 12px">
              <template #message>
                <a-space direction="vertical" style="width: 100%">
                  <div>
                    <strong>{{ getFieldReviewMark(compareModalRecord, compareModalGroupKey)?.mark_type === 'exclude' ? '排除统计' : '异常说明，计入不匹配' }}</strong>
                    <a-button type="link" size="small" danger :loading="markClearing" @click="handleClearMark">清除标记</a-button>
                  </div>
                  <div v-if="getFieldReviewMark(compareModalRecord, compareModalGroupKey)?.reason">原因：{{ getFieldReviewMark(compareModalRecord, compareModalGroupKey).reason }}</div>
                  <div v-if="getFieldReviewMark(compareModalRecord, compareModalGroupKey)?.note">备注：{{ getFieldReviewMark(compareModalRecord, compareModalGroupKey).note }}</div>
                </a-space>
              </template>
            </a-alert>
          </template>
          <a-empty v-else description="暂无人工标记" style="margin-bottom: 12px" />

          <a-form layout="vertical" size="small">
            <a-form-item label="标记类型">
              <a-select v-model:value="markForm.markType">
                <a-select-option value="exclude">排除统计</a-select-option>
                <a-select-option value="mismatch_note">异常说明，计入不匹配</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="原因">
              <a-select v-model:value="markForm.reason" placeholder="选择原因" allow-clear>
                <a-select-option v-for="r in markReasonOptions" :key="r" :value="r">{{ r }}</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="备注">
              <a-textarea v-model:value="markForm.note" :rows="2" placeholder="可选：补充说明" />
            </a-form-item>
            <a-form-item>
              <a-button type="primary" :loading="markSaving" @click="handleSaveMark">保存标记</a-button>
            </a-form-item>
          </a-form>
        </div>
      </template>
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
import { audioApi, resultApi, modelApi, testApi, promptTemplateApi, patientApi } from '@/api/client'
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
    const accuracyMode = ref<'without_remark' | 'with_remark'>('without_remark')
    const recordNoteDraft = ref('')
    const recordNoteSaving = ref(false)
    const attributionKeyword = ref('')
    const attributionFieldFilter = ref<string | undefined>(undefined)
    const attributionStatusFilter = ref<string | undefined>(undefined)
    const attributionLevelFilter = ref<string | undefined>(undefined)
    const attributionErrorTypeFilter = ref<string | undefined>(undefined)
    const attributionOnlyMarked = ref(false)
    const attributionOnlyFollicle = ref(false)

    type FollicleCompareSummary = {
      matched: number
      denominator: number
      rate: number
      missing: { size: string; count: number }[]
      extra: { size: string; count: number }[]
      status: MatchStatus
    }

    const fieldColumns = [
      { key: 'right_follicle_match', label: '右卵泡', group: 'right_follicle' },
      { key: 'left_follicle_match', label: '左卵泡', group: 'left_follicle' },
      { key: 'endometrium_thickness_match', label: '内膜厚度', group: 'endometrium_thickness' },
      { key: 'endometrium_type_match', label: '内膜类型', group: 'endometrium_type' },
      { key: 'right_ovary_match', label: '右卵巢', group: 'right_ovary' },
      { key: 'left_ovary_match', label: '左卵巢', group: 'left_ovary' },
    ]

    const follicleRateColumns = [
      { key: 'right_follicle_rate', label: '右卵泡正确率', group: 'right_follicle' },
      { key: 'left_follicle_rate', label: '左卵泡正确率', group: 'left_follicle' },
    ]

    // 字段组专项对比配置
    const compareFieldGroups: Record<string, { title: string; fields: { key: string; label: string }[] }> = {
      right_follicle: {
        title: '右卵泡',
        fields: [
          { key: 'right_follicle_total', label: '右卵泡总数' },
          { key: 'right_follicles', label: '右卵泡明细' },
        ],
      },
      left_follicle: {
        title: '左卵泡',
        fields: [
          { key: 'left_follicle_total', label: '左卵泡总数' },
          { key: 'left_follicles', label: '左卵泡明细' },
        ],
      },
      endometrium_thickness: {
        title: '内膜厚度',
        fields: [
          { key: 'endometrium_thickness', label: '内膜厚度' },
        ],
      },
      endometrium_type: {
        title: '内膜类型',
        fields: [
          { key: 'endometrium_type', label: '内膜类型' },
        ],
      },
      right_ovary: {
        title: '右卵巢',
        fields: [
          { key: 'right_ovary_length', label: '右卵巢长' },
          { key: 'right_ovary_width', label: '右卵巢宽' },
        ],
      },
      left_ovary: {
        title: '左卵巢',
        fields: [
          { key: 'left_ovary_length', label: '左卵巢长' },
          { key: 'left_ovary_width', label: '左卵巢宽' },
        ],
      },
    }

    // 字段专项对比弹窗状态
    const compareModalOpen = ref(false)
    const compareModalRecord = ref<any | null>(null)
    const compareModalGroupKey = ref<string>('')
    const compareModalMarkRefreshKey = ref(0) // 强制刷新标记 UI

    const compareModalGroupTitle = computed(() => compareFieldGroups[compareModalGroupKey.value]?.title || '')

    function openFieldCompare(record: any, groupKey: string) {
      compareModalRecord.value = { ...record }
      compareModalGroupKey.value = groupKey
      compareModalOpen.value = true
    }

    // 保存标记后的刷新回调
    async function onFieldMarkSaved(_savedMark: any) {
      compareModalMarkRefreshKey.value++
      // 刷新列表数据（包含新标记）
      await store.fetchRecords()
      // 更新弹窗中的记录
      const fresh = store.records.find((r: any) => r.id === compareModalRecord.value?.id)
      if (fresh) compareModalRecord.value = { ...fresh }
    }

    async function onFieldMarkCleared() {
      compareModalMarkRefreshKey.value++
      await store.fetchRecords()
      const fresh = store.records.find((r: any) => r.id === compareModalRecord.value?.id)
      if (fresh) compareModalRecord.value = { ...fresh }
    }

    // 人工标记表单与操作
    const markSaving = ref(false)
    const markClearing = ref(false)
    const markForm = reactive({ markType: 'exclude', reason: '', note: '' })

    const markReasonOptions = computed(() =>
      markForm.markType === 'exclude'
        ? ['收音设备问题', '录音缺失/不完整', '真实 B 超数据疑似错误', '非本次评估范围', '暂时排查', '其他']
        : ['ASR 漏识别', 'ASR 错识别', 'LLM 未提取', 'LLM 提取错误', '左右侧混淆', '数量统计错误', '尺寸解析错误', '格式不规范', '其他']
    )

    async function handleSaveMark() {
      if (!compareModalRecord.value) return
      markSaving.value = true
      try {
        await patientApi.saveFieldReviewMark(compareModalRecord.value.id, {
          field_group: compareModalGroupKey.value,
          field_key: null,
          mark_type: markForm.markType,
          reason: markForm.reason || null,
          note: markForm.note || null,
        })
        message.success('标记已保存')
        await onFieldMarkSaved(null)
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '保存失败')
      } finally {
        markSaving.value = false
      }
    }

    async function handleClearMark() {
      if (!compareModalRecord.value) return
      markClearing.value = true
      try {
        await patientApi.clearFieldReviewMark(compareModalRecord.value.id, compareModalGroupKey.value)
        message.success('标记已清除')
        await onFieldMarkCleared()
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '清除失败')
      } finally {
        markClearing.value = false
      }
    }

    const fieldColumnMap = fieldColumns.reduce((acc, item) => {
      acc[item.key] = item
      return acc
    }, {} as Record<string, { key: string; label: string; group: string }>)

    const filteredRecords = computed(() => {
      if (!searchText.value.trim()) return allRecords.value
      const q = searchText.value.trim().toLowerCase()
      return allRecords.value.filter((r) => r.record_id.toLowerCase().includes(q))
    })

    // 响应式表格列定义
    const tableColumns = computed(() => [
      { title: '病历号', dataIndex: 'record_id', key: 'record_id', ellipsis: true },
      { title: '日期', dataIndex: 'date', key: 'date' },
      { title: '备注', dataIndex: 'note', key: 'note', ellipsis: true },
      { title: '录音', dataIndex: 'has_audio', key: 'has_audio' },
      { title: '结果', dataIndex: 'has_result', key: 'has_result' },
      { title: 'ASR', dataIndex: 'asr_status', key: 'asr_status', ellipsis: true },
      { title: 'LLM', dataIndex: 'llm_status', key: 'llm_status', ellipsis: true },
      {
        title: '准确率',
        dataIndex: 'accuracy',
        key: 'accuracy',
        align: 'center' as const,
        sorter: (a: PatientExamination, b: PatientExamination) => getAccuracySortValue(a) - getAccuracySortValue(b),
      },
      ...follicleRateColumns.map((field) => ({
        title: field.label,
        dataIndex: field.key,
        key: field.key,
        align: 'center' as const,
        sorter: (a: PatientExamination, b: PatientExamination) => getFollicleRateSortValue(a, field.group) - getFollicleRateSortValue(b, field.group),
      })),
      ...fieldColumns.map((field) => ({
        title: field.label,
        dataIndex: field.key,
        key: field.key,
        align: 'center' as const,
      })),
      { title: '操作', dataIndex: 'action', key: 'action' },
    ])

    // 可拖拽列宽
    const columnWidths = ref<Record<string, number>>({})
    const resizableColumns = computed(() =>
      tableColumns.value.map((col) => ({
        ...col,
        width: columnWidths.value[col.dataIndex] || (col as any).width,
      }))
    )

    function getAccuracyValue(record: PatientExamination): number | undefined {
      const adjusted = getAdjustedAccuracyValue(record)
      if (adjusted != null) return adjusted

      const latest = record.latest_llm as any
      if (!latest) return undefined
      if (accuracyMode.value === 'with_remark') {
        return latest.accuracy_with_remark ?? latest.evaluation_with_remark?.accuracy ?? calculateAccuracyFromEvaluation(latest.evaluation, true) ?? latest.accuracy
      }
      return latest.accuracy_without_remark ?? calculateAccuracyFromEvaluation(latest.evaluation, false) ?? latest.accuracy
    }

    function getAdjustedAccuracyValue(record: PatientExamination): number | undefined {
      const latest = record.latest_llm as any
      if (!latest) return undefined

      // 数据管理列表准确率按“业务字段组”计算，而不是后端 evaluation 的细字段数。
      // 不含备注 = 6 项：右卵泡、左卵泡、内膜厚度、内膜类型、右卵巢、左卵巢
      // 含备注 = 7 项：上述 6 项 + 备注
      // 人工排除 exclude 不进入分母；异常说明 mismatch_note 仍按不匹配计入。
      const groups = fieldColumns.map((field) => field.group)
      if (accuracyMode.value === 'with_remark') groups.push('remark')

      const statuses = groups
        .map((group) => getMatchStatus(record, group))
        .filter((status) => status !== 'empty' && status !== 'ignored')
      if (!statuses.length) return undefined
      const matched = statuses.filter((status) => status === 'match').length
      return Number((matched / statuses.length).toFixed(4))
    }

    function getAccuracySortValue(record: PatientExamination): number {
      const value = getAccuracyValue(record)
      return typeof value === 'number' ? value : -1
    }

    function getFollicleRateSortValue(record: PatientExamination, group: string): number {
      const summary = getFollicleCompareSummary(record, group)
      if (!summary || summary.status === 'empty') return -1
      return summary.rate
    }

    const follicleRateColumnMap = computed(() => {
      const map = new Map<string, { key: string; label: string; group: string }>()
      for (const col of follicleRateColumns) map.set(col.key, col)
      return map
    })

    function getFollicleRateColumn(dataIndex: any) {
      return follicleRateColumnMap.value.get(String(dataIndex || '')) || null
    }

    function follicleRateDisplayText(record: PatientExamination, group: string): string {
      const summary = getFollicleCompareSummary(record, group)
      if (!summary || summary.status === 'empty') return '-'
      return `${(summary.rate * 100).toFixed(1)}%`
    }

    function follicleRateTagColor(record: PatientExamination, group: string): string {
      const summary = getFollicleCompareSummary(record, group)
      if (!summary || summary.status === 'empty') return 'default'
      if (summary.rate >= 1) return 'green'
      if (summary.rate >= 0.8) return 'orange'
      return 'red'
    }

    function calculateAccuracyFromEvaluation(evaluation: any, includeRemark: boolean): number | undefined {
      const fields = evaluation?.fields
      if (!fields || typeof fields !== 'object') return undefined
      const entries = Object.entries(fields).filter(([key]) => includeRemark || key !== 'remark')
      if (!entries.length) return undefined
      const correct = entries.filter(([, value]: any) => value?.match === true).length
      return Number((correct / entries.length).toFixed(4))
    }

    const follicleAverageStats = computed(() => follicleRateColumns.map((field) => {
      const values = filteredRecords.value
        .map((record) => getFollicleCompareSummary(record, field.group))
        .filter((summary): summary is FollicleCompareSummary => !!summary && summary.status !== 'empty')
        .map((summary) => summary.rate)
      const total = values.length
      const average = total ? values.reduce((sum, value) => sum + value, 0) / total : 0
      return {
        ...field,
        total,
        average,
      }
    }))

    const fieldMatchStats = computed(() => fieldColumns.map((field) => {
      const statuses = filteredRecords.value
        .map((record) => getMatchStatus(record, field.group))
        .filter((status) => status !== 'empty' && status !== 'ignored')
      const matched = statuses.filter((status) => status === 'match').length
      const total = statuses.length
      return {
        ...field,
        matched,
        total,
        rate: total ? matched / total : 0,
      }
    }))

    function getFieldColumn(dataIndex: any) {
      return fieldColumnMap[String(dataIndex || '')] || null
    }

    const fieldAttributionColumns = [
      { title: '病历号', dataIndex: 'record_id', key: 'record_id', width: 110 },
      { title: '日期', dataIndex: 'date', key: 'date', width: 105 },
      { title: '字段', dataIndex: 'field', key: 'field', width: 100 },
      { title: '状态', dataIndex: 'status', key: 'status', width: 90 },
      { title: '归因层级', dataIndex: 'attribution_level', key: 'attribution_level', width: 130 },
      { title: '错误类型', dataIndex: 'error_type', key: 'error_type', width: 150 },
      { title: '具体原因', dataIndex: 'reason', key: 'reason', ellipsis: true },
      { title: '优先级/建议', dataIndex: 'priority', key: 'priority', width: 170 },
      { title: '原人工判定', dataIndex: 'original_judgement', key: 'original_judgement', ellipsis: true },
      { title: 'ASR模型', dataIndex: 'asr_model', key: 'asr_model', width: 130 },
      { title: 'LLM模型', dataIndex: 'llm_model', key: 'llm_model', width: 120 },
      { title: '提示词模板', dataIndex: 'prompt_template', key: 'prompt_template', width: 140 },
    ]

    const fieldAttributionRows = computed(() => {
      const rows: any[] = []
      for (const record of filteredRecords.value) {
        for (const field of fieldColumns) {
          rows.push(buildFieldAttributionRow(record, field))
        }
      }
      return rows
    })

    const filteredFieldAttributionRows = computed(() => {
      const keyword = attributionKeyword.value.trim().toLowerCase()
      return fieldAttributionRows.value.filter((row) => {
        if (keyword && !String(row.record_id || '').toLowerCase().includes(keyword)) return false
        if (attributionFieldFilter.value && row.group !== attributionFieldFilter.value) return false
        if (attributionStatusFilter.value && row.status !== attributionStatusFilter.value) return false
        if (attributionLevelFilter.value && row.attribution_level !== attributionLevelFilter.value) return false
        if (attributionErrorTypeFilter.value && row.error_type !== attributionErrorTypeFilter.value) return false
        if (attributionOnlyMarked.value && !row.has_mark) return false
        if (attributionOnlyFollicle.value && !isFollicleGroup(row.group)) return false
        return true
      })
    })

    const attributionLevelOptions = computed(() => uniqueOptions(fieldAttributionRows.value.map((row) => row.attribution_level).filter((v) => v && v !== '—')))
    const attributionErrorTypeOptions = computed(() => uniqueOptions(fieldAttributionRows.value.map((row) => row.error_type).filter((v) => v && v !== '—')))

    const attributionOverallStats = computed(() => {
      const rows = filteredFieldAttributionRows.value
      const total = rows.length
      const correct = rows.filter((row) => row.status === '正确').length
      const error = rows.filter((row) => row.status === '错误').length
      const excluded = rows.filter((row) => row.status === '排除').length
      const abnormal = rows.filter((row) => row.status === '异常').length
      const missing = rows.filter((row) => row.status === '未提取').length
      const denominator = total - excluded
      const accuracy = denominator > 0 ? correct / denominator : 0
      return { total, correct, error, excluded, abnormal, missing, denominator, accuracy }
    })

    const attributionFieldStats = computed(() => fieldColumns.map((field) => {
      const rows = filteredFieldAttributionRows.value.filter((row) => row.group === field.group)
      const total = rows.length
      const correct = rows.filter((row) => row.status === '正确').length
      const error = rows.filter((row) => row.status === '错误').length
      const excluded = rows.filter((row) => row.status === '排除').length
      const abnormal = rows.filter((row) => row.status === '异常').length
      const missing = rows.filter((row) => row.status === '未提取').length
      const denominator = total - excluded
      return {
        ...field,
        total,
        correct,
        error,
        excluded,
        abnormal,
        missing,
        accuracy: denominator > 0 ? correct / denominator : 0,
      }
    }))

    function uniqueOptions(values: string[]) {
      return Array.from(new Set(values)).sort()
    }

    function buildFieldAttributionRow(record: PatientExamination, field: { key: string; label: string; group: string }) {
      const mark = getFieldReviewMark(record, field.group)
      const status = getAttributionStatus(record, field.group, mark)
      const reasonText = getAttributionReason(record, field.group, status, mark)
      return {
        key: `${record.id}-${field.group}`,
        record_id: record.record_id,
        date: formatDate(record.date),
        group: field.group,
        field: field.label,
        status,
        attribution_level: getAttributionLevel(record, field.group, status, mark),
        error_type: getAttributionErrorType(field.label, status, mark),
        reason: reasonText,
        priority: getAttributionPriority(status, mark),
        original_judgement: buildOriginalJudgement(record, field.group, status, mark),
        has_mark: !!mark,
        asr_model: record.latest_llm?.asr_model_name || record.latest_asr?.asr_model_name || '-',
        llm_model: record.latest_llm?.llm_model_name || '-',
        prompt_template: record.latest_llm?.prompt_template_name || '-',
      }
    }

    function getAttributionStatus(record: PatientExamination, group: string, mark: any): string {
      if (mark?.mark_type === 'exclude') return '排除'
      if (mark?.mark_type === 'mismatch_note') return '异常'
      const status = getMatchStatus(record, group)
      if (status === 'match') return '正确'
      if (status === 'empty') return '未提取'
      if (status === 'ignored') return '排除'
      return '错误'
    }

    function getAttributionLevel(record: PatientExamination, group: string, status: string, mark: any): string {
      if (status === '正确') return '—'
      if (status === '未提取') return '数据缺失'
      const text = `${mark?.reason || ''}${mark?.note || ''}`.toLowerCase()
      if (mark?.mark_type === 'exclude') {
        if (text.includes('收音') || text.includes('录音') || text.includes('asr')) return 'ASR/收音'
        return '人工排除'
      }
      if (mark?.mark_type === 'mismatch_note') return '人工标记'
      if (isFollicleGroup(group)) return 'ASR/LLM'
      return 'LLM提取'
    }

    function getAttributionErrorType(label: string, status: string, mark: any): string {
      if (status === '正确') return '—'
      if (status === '未提取') return '缺少结果'
      if (mark?.reason) return mark.reason
      if (status === '排除') return '人工排除'
      if (status === '异常') return '人工异常'
      return `${label}不一致`
    }

    function getAttributionReason(record: PatientExamination, group: string, status: string, mark: any): string {
      if (status === '正确') return '字段正确'
      const manual = [mark?.reason, mark?.note].filter(Boolean).join('；')
      const lines = isFollicleGroup(group) ? follicleMismatchLines(record, group) : []
      const detail = lines.length ? lines.join('；') : ''
      if (manual && detail) return `${manual}；${detail}`
      if (manual) return manual
      if (detail) return detail
      if (status === '未提取') return '缺少 LLM 提取结果或真实 B 超数据'
      return 'LLM 提取结果与真实 B 超结果不一致'
    }

    function getAttributionPriority(status: string, mark: any): string {
      if (status === '正确') return '保持现有规则'
      if (mark?.mark_type === 'exclude') return '不计入提示词准确率'
      if (status === '未提取') return '补齐数据后再判断'
      return '优先复核 ASR 文本与提示词抽取规则'
    }

    function buildOriginalJudgement(record: PatientExamination, group: string, status: string, mark: any): string {
      const lines = isFollicleGroup(group) ? follicleMismatchLines(record, group) : []
      if (mark?.mark_type === 'exclude') {
        return ['⚠️排除', ...lines].join('；')
      }
      if (mark?.mark_type === 'mismatch_note') {
        return ['❌异常', ...lines].join('；')
      }
      if (status === '正确') {
        if (isFollicleGroup(group)) return '✅100.0%'
        return '✅'
      }
      if (status === '未提取') return '-'
      const display = fieldStatusDisplayText(record, group)
      return [display, ...lines].filter(Boolean).join('；')
    }

    async function saveRecordNote() {
      if (!selectedRecord.value) return
      recordNoteSaving.value = true
      try {
        const noteVal = recordNoteDraft.value || ''
        const res: any = await audioApi.updatePatientNote(selectedRecord.value.id, noteVal)
        const note = res?.note ?? noteVal
        store.selectedRecord = { ...selectedRecord.value, note } as any
        const target = store.records.find((record) => record.id === selectedRecord.value?.id)
        if (target) target.note = note
        message.success('检查备注已保存')
      } catch (e: any) {
        message.error(e?.response?.data?.detail || e?.message || '保存备注失败')
      } finally {
        recordNoteSaving.value = false
      }
    }

    function selectBatch(date: string | null) { store.selectBatch(date) }
    function openDetail(record: PatientExamination) {
  store.openDrawer(record)
}
    function closeDrawer() { store.closeDrawer() }
    function onRowClick(record: PatientExamination) {
      return { onClick: () => openDetail(record), style: { cursor: 'pointer' } }
    }

    type MatchStatus = 'match' | 'mismatch' | 'empty' | 'ignored'

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

    function getPromptTemplateNameById(templateId: number | undefined): string {
      if (!templateId) return ''
      const tmpl = promptTemplates.value.find((t: any) => t.id === templateId)
      return tmpl?.name || ''
    }

    function getListAsrStatusColor(record: PatientExamination): string {
      const linkedAsr = record.latest_llm?.asr_result_id ? record.latest_llm : null
      const status = linkedAsr?.asr_status || record.latest_asr?.status
      if (!status) return 'default'
      if (status === 'success') return 'blue'
      if (status === 'failed') return 'red'
      if (status === 'running') return 'orange'
      return 'default'
    }

    function getListAsrStatusText(record: PatientExamination): string {
      const linkedAsr = record.latest_llm?.asr_result_id ? record.latest_llm : null
      const name = linkedAsr?.asr_model_name || record.latest_asr?.asr_model_name
      const status = linkedAsr?.asr_status || record.latest_asr?.status
      if (!name) return '未转写'
      if (status === 'failed') return `${name} / 失败`
      if (status === 'running') return `${name} / 转写中`
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
      // 优先检查人工标记
      const mark = getFieldReviewMark(record, group)
      if (mark?.mark_type === 'exclude') return 'ignored'
      if (mark?.mark_type === 'mismatch_note') return 'mismatch'

      if (!record.latest_llm || !record.result) return 'empty'
      if (group === 'right_follicle') {
        return getFollicleMatchStatus(record, group)
      }
      if (group === 'left_follicle') {
        return getFollicleMatchStatus(record, group)
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
      if (status === 'ignored') return 'orange'
      return 'default'
    }

    function matchTagText(status: MatchStatus): string {
      if (status === 'match') return '✅'
      if (status === 'mismatch') return '❌'
      if (status === 'ignored') return '⚠️'
      return '-'
    }

    function fieldStatusTagColor(record: PatientExamination, group: string): string {
      const mark = getFieldReviewMark(record, group)
      if (mark?.mark_type === 'exclude') return 'orange'
      if (mark?.mark_type === 'mismatch_note') return 'red'
      if (isFollicleGroup(group)) {
        const summary = getFollicleCompareSummary(record, group)
        if (!summary || summary.status === 'empty') return 'default'
        if (summary.rate >= 1) return 'green'
        if (summary.rate >= 0.8) return 'orange'
        return 'red'
      }
      return matchTagColor(getMatchStatus(record, group))
    }

    function fieldStatusDisplayText(record: PatientExamination, group: string): string {
      const mark = getFieldReviewMark(record, group)
      if (mark?.mark_type === 'exclude') return '⚠️ 排除'
      if (mark?.mark_type === 'mismatch_note') {
        const reason = String(mark.reason || '').trim()
        return reason ? `❌ ${reason}` : '❌ 已标注'
      }
      if (isFollicleGroup(group)) {
        const summary = getFollicleCompareSummary(record, group)
        if (!summary || summary.status === 'empty') return '-'
        return `${summary.status === 'match' ? '✅' : '❌'} ${(summary.rate * 100).toFixed(1)}%`
      }
      return matchTagText(getMatchStatus(record, group))
    }

    function isFollicleGroup(group: string): boolean {
      return group === 'right_follicle' || group === 'left_follicle'
    }

    function getFollicleKeys(group: string): { totalKey: 'right_follicle_total' | 'left_follicle_total'; listKey: 'right_follicles' | 'left_follicles' } | null {
      if (group === 'right_follicle') return { totalKey: 'right_follicle_total', listKey: 'right_follicles' }
      if (group === 'left_follicle') return { totalKey: 'left_follicle_total', listKey: 'left_follicles' }
      return null
    }

    function getFollicleMatchStatus(record: PatientExamination, group: string): MatchStatus {
      const summary = getFollicleCompareSummary(record, group)
      if (summary) return summary.status
      const keys = getFollicleKeys(group)
      if (!keys) return 'empty'
      const detail = fieldMatch(record, keys.listKey)
      return detail !== 'empty' ? detail : fieldMatch(record, keys.totalKey)
    }

    function getFollicleCompareSummary(record: any, group: string): FollicleCompareSummary | null {
      const keys = getFollicleKeys(group)
      if (!keys) return null
      const structured = normalizeStructured(getLatestLlmStructured(record))
      const gt = getLatestGroundTruth(record)
      if (!structured || !gt) return null
      return compareFollicleSets(structured[keys.listKey], gt[keys.listKey])
    }

    function follicleMismatchLines(record: PatientExamination, group: string): string[] {
      const summary = getFollicleCompareSummary(record, group)
      if (!summary || summary.status === 'empty' || summary.status === 'match') return []
      const lines: string[] = []
      if (summary.missing.length) lines.push(`漏识别：${formatFollicleDiffItems(summary.missing)}`)
      if (summary.extra.length) lines.push(`多识别：${formatFollicleDiffItems(summary.extra)}`)
      return lines
    }

    function formatFollicleDiffItems(items: { size: string; count: number }[]): string {
      return items.map((item) => `${item.size}*${item.count}`).join('、')
    }

    // 兼容 structured_result 和 structured 字段
    function getLatestLlmStructured(record: any): any {
      return record?.latest_llm?.structured_result
        || record?.latest_llm?.structured
        || record?.structured_result
        || record?.structured
        || {}
    }

    // 兼容 ground_truth 和 result 字段
    function getLatestGroundTruth(record: any): any {
      return record?.latest_llm?.ground_truth
        || record?.ground_truth
        || record?.result
        || {}
    }

    // 统一值格式化
    function formatCompareValue(val: any): string {
      if (val == null || val === '') return '-'
      if (Array.isArray(val)) {
        if (!val.length) return '-'
        return val.map((v: any) => {
          if (v && typeof v === 'object' && ('size' in v || 'count' in v)) {
            return `${v.size ?? '?'}×${v.count ?? 1}`
          }
          if (v && typeof v === 'object') return JSON.stringify(v)
          return String(v)
        }).join('；')
      }
      if (typeof val === 'object') return JSON.stringify(val, null, 2)
      return String(val)
    }

    // 字段组到字段的映射（用于查找标记）
    const FIELD_TO_GROUP: Record<string, string> = {
      right_follicle_total: 'right_follicle',
      right_follicles: 'right_follicle',
      left_follicle_total: 'left_follicle',
      left_follicles: 'left_follicle',
      endometrium_thickness: 'endometrium_thickness',
      endometrium_type: 'endometrium_type',
      right_ovary_length: 'right_ovary',
      right_ovary_width: 'right_ovary',
      left_ovary_length: 'left_ovary',
      left_ovary_width: 'left_ovary',
    }

    function getFieldReviewMark(record: any, fieldOrGroup: string): any | null {
      const marks = record?.field_review_marks || record?.latest_llm?.field_review_marks || []
      if (!marks.length) return null
      // 优先精确匹配 field_key
      let mark = marks.find((m: any) => m.field_key === fieldOrGroup)
      if (mark) return mark
      // 匹配 field_group
      const group = FIELD_TO_GROUP[fieldOrGroup] || fieldOrGroup
      mark = marks.find((m: any) => m.field_group === group)
      return mark || null
    }

    // 字段专项弹窗匹配判断（含人工标记逻辑）
    function compareModalFieldStatus(record: any, fieldKey: string, llmVal: any, gtVal: any): MatchStatus {
      const manualMark = getFieldReviewMark(record, fieldKey)
      if (manualMark?.mark_type === 'exclude') return 'ignored'
      if (manualMark?.mark_type === 'mismatch_note') return 'mismatch'

      const item = record?.latest_llm?.evaluation?.fields?.[fieldKey]
      if (item?.match != null) return item.match ? 'match' : 'mismatch'

      if (llmVal == null && gtVal == null) return 'empty'
      if (llmVal == null || gtVal == null) return 'mismatch'

      if (fieldKey === 'right_follicles' || fieldKey === 'left_follicles') {
        const llmList = normalizeFollicles(llmVal)
        const gtList = normalizeFollicles(gtVal)
        if (!llmList.length && !gtList.length) return 'empty'
        return JSON.stringify(llmList) === JSON.stringify(gtList) ? 'match' : 'mismatch'
      }

      return normalizeComparableText(llmVal) === normalizeComparableText(gtVal) ? 'match' : 'mismatch'
    }

    // 获取字段专项对比表格数据
    function getFieldCompareRows(record: any, groupKey: string): any[] {
      const group = compareFieldGroups[groupKey]
      if (!group) return []
      const structured = getLatestLlmStructured(record)
      const gt = getLatestGroundTruth(record)

      return group.fields.map((f) => {
        const llmVal = structured?.[f.key]
        const gtVal = gt?.[f.key]
        const match = compareModalFieldStatus(record, f.key, llmVal, gtVal)
        return {
          field: f.key,
          label: f.label,
          llmValue: formatCompareValue(llmVal),
          gtValue: formatCompareValue(gtVal),
          match,
        }
      })
    }

    // 真实值格式化（向后兼容）
    function formatGtValue(fieldKey: string, val: any): string {
      return formatCompareValue(val)
    }

    // 列表页本地字段匹配计算
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
      return normalizeComparableText(llmVal) === normalizeComparableText(gtVal) ? 'match' : 'mismatch'
    }

    function normalizeComparableText(value: any): string {
      const text = String(value ?? '').trim()
      if (!text) return ''
      const num = Number(text)
      if (Number.isFinite(num)) return String(Math.round(num * 100) / 100)
      return text
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

    function formatFolliclesForEdit(value: any): string {
      return normalizeFolliclesForEdit(value).map((f) => `${f.size}x${f.count}`).join('\n')
    }

    function normalizeFolliclesForEdit(value: any): { size: string; count: number }[] {
      if (Array.isArray(value)) return normalizeFollicles(value)
      if (typeof value === 'string') {
        const text = value.trim()
        if (!text) return []
        try {
          const parsed = JSON.parse(text)
          if (Array.isArray(parsed)) return normalizeFollicles(parsed)
        } catch {
          // 普通文本继续走正则解析
        }
        return parseFollicleLines(text)
      }
      return []
    }

    function openEditBUltra() {
      const r = (selectedRecord.value?.result || {}) as any
      bUltraForm.right_follicle_total = r.right_follicle_total ?? null
      bUltraForm.left_follicle_total = r.left_follicle_total ?? null
      bUltraForm.right_follicles = normalizeFolliclesForEdit(r.right_follicles)
      bUltraForm.left_follicles = normalizeFolliclesForEdit(r.left_follicles)
      bUltraForm.right_follicles_raw = formatFolliclesForEdit(r.right_follicles)
      bUltraForm.left_follicles_raw = formatFolliclesForEdit(r.left_follicles)
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
      const text = raw.trim()
      const result: { size: string; count: number }[] = []
      const pattern = /(\d+(?:\.\d+)?)\s*(?:[xX×﹡*]\s*(\d+))?/g
      let match: RegExpExecArray | null
      while ((match = pattern.exec(text)) !== null) {
        const size = normalizeSize(match[1])
        const count = match[2] ? Number(match[2]) : 1
        if (!size || !Number.isFinite(count) || count <= 0) {
          throw new Error(`无法解析卵泡明细: "${raw}"，请使用格式如 10x2、12×1、15*3 或 13.5`)
        }
        result.push({ size, count })
      }
      if (!result.length) {
        throw new Error(`无法解析卵泡明细: "${raw}"，请使用格式如 10x2、12×1、15*3 或 13.5`)
      }
      return normalizeFollicles(result)
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
          endometrium_thickness: bUltraForm.endometrium_thickness ?? null,
          endometrium_type: bUltraForm.endometrium_type || null,
          right_ovary_length: bUltraForm.right_ovary_length ?? null,
          right_ovary_width: bUltraForm.right_ovary_width ?? null,
          left_ovary_length: bUltraForm.left_ovary_length ?? null,
          left_ovary_width: bUltraForm.left_ovary_width ?? null,
          remark: bUltraForm.remark || null,
        }
        payload.right_follicle_total = right_follicles.reduce((s, f) => s + f.count, 0)
        payload.left_follicle_total = left_follicles.reduce((s, f) => s + f.count, 0)

        const examRecordId = selectedRecord.value.id
        const res: any = await resultApi.updateBUltraResult(examRecordId, payload)
        const updated = res?.data || res
        message.success('真实 B 超结果已保存')
        showBUltraModal.value = false
        store.selectedRecord = { ...selectedRecord.value, result: updated } as any
        const target = store.records.find((record) => record.id === examRecordId)
        if (target) target.result = updated
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '保存失败')
      } finally {
        bUltraSaving.value = false
      }
    }

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

      // 同 rank 时一律取更新时间更新者；is_current 只保留为展示字段，
      // 不再影响默认选择，避免最新豆包结果被历史 FunASR current 覆盖。
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

    function pickLatestSuccessfulAsrResult(results: any[]): any | null {
      return results
        .filter((r: any) => r?.status === 'success')
        .sort((a: any, b: any) => {
          const tb = b.created_at ? new Date(b.created_at).getTime() : 0
          const ta = a.created_at ? new Date(a.created_at).getTime() : 0
          if (tb !== ta) return tb - ta
          return Number(b.id || 0) - Number(a.id || 0)
        })[0] || null
    }

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
      stage: '',
      asrDone: 0,
      asrTotal: 0,
    })
    const batchFailures = ref<{ id: number; record_id: string; date: string; stage: string; error: string }[]>([])

    async function loadModels() {
      try {
        const [asr, llm] = await Promise.all([modelApi.list('asr'), modelApi.list('llm')])
        // 只显示 active 模型
        asrModels.value = (asr as any[]).filter((m: any) => m.status === 'active')
        llmModels.value = (llm as any[]).filter((m: any) => m.status === 'active')
        if (llmModels.value.length > 0) {
          llmModelId.value = llmModels.value.find((m: any) => m.is_default)?.id || llmModels.value[0].id
          batchLlmModelId.value = llmModels.value.find((m: any) => m.is_default)?.id || llmModels.value[0].id
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

      // 自动选择最佳模型：默认展示最新一次成功 ASR 记录本身，而不是历史 is_current。
      const map = asrResultByModelId.value
      const latestSuccess = pickLatestSuccessfulAsrResult(asrResultsAll.value)
      let bestMid: number | undefined
      if (latestSuccess) {
        bestMid = latestSuccess.asr_model_id
        asrModelId.value = bestMid
        selectedAsrResult.value = latestSuccess
        return
      }
      // 其次从每个模型代表结果里找 success
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

    async function exportLatestLlmForFilteredRecords() {
      const patientIds = filteredRecords.value.map((record) => record.id).filter(Boolean)
      if (!patientIds.length) {
        message.warning('当前表格没有可导出的检查记录')
        return
      }
      try {
        const data: any = await audioApi.exportLatestLlmResults(patientIds)
        const blob = data instanceof Blob
          ? data
          : new Blob([data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        const batchName = selectedBatch.value ? formatDate(selectedBatch.value).replace(/-/g, '') : 'all'
        const keyword = searchText.value.trim() ? `_${searchText.value.trim()}` : ''
        link.href = url
        link.download = `LLM_latest_${batchName}${keyword}_${patientIds.length}records.xlsx`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
        message.success(`已导出 ${patientIds.length} 条最新 LLM 记录`)
      } catch (e: any) {
        message.error(`导出失败: ${e?.response?.data?.detail || e?.message || ''}`)
      }
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

    function parseSseError(event?: any): string {
      if (!event?.data) return 'ASR 请求失败或连接中断'
      try {
        const parsed = JSON.parse(String(event.data))
        return parsed.message || parsed.detail || String(event.data)
      } catch {
        return String(event.data)
      }
    }

    function isUsableAsrResult(result: any): boolean {
      return result?.status === 'success' && typeof result.full_transcript === 'string' && result.full_transcript.trim().length > 0
    }

    function waitForAsrComplete(record: PatientExamination, modelId: number): Promise<any> {
      return new Promise((resolve, reject) => {
        const es = patientApi.runAsrSSE(record.id, modelId)
        let settled = false
        const segCount = Math.max(record.segs?.length || 0, 1)
        const timeoutMs = Math.max(120000, segCount * 60000)
        const timeout = window.setTimeout(() => {
          if (settled) return
          settled = true
          es.close()
          reject(new Error(`ASR 超时（${Math.round(timeoutMs / 1000)} 秒）`))
        }, timeoutMs)

        const finish = async (event?: any) => {
          if (settled) return
          let parsed: any = {}
          try {
            parsed = event?.data ? JSON.parse(String(event.data)) : {}
          } catch {
            parsed = {}
          }
          if (!isUsableAsrResult(parsed)) {
            try {
              const persisted = await getOrReuseAsrForRecord(record, modelId)
              if (persisted) {
                settled = true
                window.clearTimeout(timeout)
                es.close()
                resolve(persisted)
                return
              }
            } catch {
              // fall through to the explicit failure below
            }
            settled = true
            window.clearTimeout(timeout)
            es.close()
            reject(new Error(parsed?.message || 'ASR 执行完成但未返回有效文本'))
            return
          }
          settled = true
          window.clearTimeout(timeout)
          es.close()
          resolve(parsed)
        }

        const fail = (event?: any) => {
          if (settled) return
          settled = true
          window.clearTimeout(timeout)
          es.close()
          reject(new Error(parseSseError(event)))
        }

        es.addEventListener('progress', (event: any) => {
          try {
            const parsed = JSON.parse(String(event.data || '{}'))
            batchProgress.stage = 'ASR'
            batchProgress.asrTotal = parsed.total || batchProgress.asrTotal || segCount
            if (parsed.stage === 'segment_start') {
              batchProgress.asrDone = Math.max(0, (parsed.seg_index || 1) - 1)
            }
          } catch { /* ignore progress parse errors */ }
        })
        es.addEventListener('segment', (event: any) => {
          try {
            const parsed = JSON.parse(String(event.data || '{}'))
            batchProgress.stage = 'ASR'
            batchProgress.asrTotal = parsed.total || batchProgress.asrTotal || segCount
            batchProgress.asrDone = parsed.seg_index || batchProgress.asrDone
          } catch { /* ignore segment parse errors */ }
        })
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
        .filter((r: any) => r.asr_model_id === modelId && isUsableAsrResult(r))
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

    async function ensureAsrForRecord(record: PatientExamination, modelId: number) {
      const reused = await getOrReuseAsrForRecord(record, modelId)
      if (reused) return reused
      if (!record.segs?.length) throw new Error('该检查记录无录音文件')
      const completed = await waitForAsrComplete(record, modelId)
      await waitForLatestAsrVisible(record)
      const persisted = await getOrReuseAsrForRecord(record, modelId)
      return persisted || completed
    }

    async function runLlmForRecord(record: PatientExamination, preparedAsrResultId?: number) {
      if (!batchLlmModelId.value) throw new Error('未选择 LLM 模型')
      if (!batchPromptContent.value) throw new Error('未选择提示词模板')

      let asrResultId: number | undefined = preparedAsrResultId
      if (batchAsrModelId.value) {
        const asr = asrResultId ? null : await ensureAsrForRecord(record, batchAsrModelId.value)
        asrResultId = asrResultId || asr?.id
        if (!asrResultId) throw new Error('ASR 执行失败，无可用结果')
      } else {
        // 非批量模式：使用当前 ASR
        const asr = await getCurrentAsrForRecord(record)
        if (!asr?.id || !isUsableAsrResult(asr)) throw new Error('该检查记录没有可复用的 ASR 转写结果')
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
      batchProgress.stage = ''
      batchProgress.asrDone = 0
      batchProgress.asrTotal = 0
      batchFailures.value = []

      try {
        for (const record of targets) {
          batchProgress.current = `${record.record_id} ${formatDate(record.date)}`
          batchProgress.stage = ''
          batchProgress.asrDone = 0
          batchProgress.asrTotal = record.segs?.length || 0
          let stage = 'ASR'
          let preparedAsrResultId: number | undefined
          try {
            if (mode === 'asr' || mode === 'both') {
              stage = 'ASR'
              const asr = await ensureAsrForRecord(record, batchAsrModelId.value!)
              preparedAsrResultId = asr?.id
              await waitForLatestAsrVisible(record)
            }
            if (mode === 'llm' || mode === 'both') {
              stage = 'LLM'
              batchProgress.stage = 'LLM'
              await runLlmForRecord(record, preparedAsrResultId)
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
        if (batchProgress.failed) {
          message.warning(`批量执行完成：成功 ${batchProgress.success} 条，失败 ${batchProgress.failed} 条`)
        } else {
          message.success(`批量执行完成：成功 ${batchProgress.success} 条`)
        }
      } finally {
        batchRunning.value = false
        batchMode.value = ''
        batchProgress.current = ''
        batchProgress.stage = ''
        batchProgress.asrDone = 0
        batchProgress.asrTotal = 0
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
      const match = normalizeComparableText(llmVal) === normalizeComparableText(gtVal)
      return correct ? match : !match && llmVal !== undefined
    }

    function detailGroupTextColor(group: 'right_ovary' | 'left_ovary'): string {
      const fields = group === 'right_ovary'
        ? ['right_ovary_length', 'right_ovary_width']
        : ['left_ovary_length', 'left_ovary_width']
      const statuses = fields.map((field) => {
        if (compareField(field, true)) return 'match'
        if (compareField(field, false)) return 'mismatch'
        return 'empty'
      }) as MatchStatus[]
      const status = mergeStatus(statuses)
      if (status === 'match') return '#52c41a'
      if (status === 'mismatch') return '#ff4d4f'
      return 'inherit'
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
      const found = normalizeFollicles(llmList).find((f: any) => f.size === normalizedSize && f.count >= normalizedCount)
      return found ? 'status-match' : 'status-mismatch'
    }

    function compareFolls(llmFolls: any, gtFolls: any): { size: string; count: number; status: string }[] {
      const result: { size: string; count: number; status: string }[] = []
      const summary = compareFollicleSets(llmFolls, gtFolls)
      const llmList = normalizeFollicles(llmFolls)
      const gtCountMap = follicleCountMap(normalizeFollicles(gtFolls))

      for (const f of llmList) {
        const gtCount = gtCountMap.get(f.size) || 0
        const matchedCount = Math.min(f.count, gtCount)
        if (matchedCount > 0) result.push({ size: f.size, count: matchedCount, status: 'match' })
        const extraCount = f.count - matchedCount
        if (extraCount > 0) result.push({ size: f.size, count: extraCount, status: 'mismatch' })
      }

      for (const f of summary.missing) result.push({ size: f.size, count: f.count, status: 'missing' })
      return result
    }

    function normalizeSize(size: any): string {
      const text = String(size ?? '').trim()
      if (!text) return ''
      const n = Number(text)
      if (Number.isFinite(n)) return String(n)
      return text
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

    function follicleCountMap(list: { size: string; count: number }[]): Map<string, number> {
      const map = new Map<string, number>()
      for (const item of list) {
        map.set(item.size, (map.get(item.size) || 0) + item.count)
      }
      return map
    }

    function compareFollicleSets(llmFolls: any, gtFolls: any): FollicleCompareSummary {
      const llmList = normalizeFollicles(llmFolls)
      const gtList = normalizeFollicles(gtFolls)
      const llmMap = follicleCountMap(llmList)
      const gtMap = follicleCountMap(gtList)
      const allSizes = new Set<string>([...llmMap.keys(), ...gtMap.keys()])
      const missing: { size: string; count: number }[] = []
      const extra: { size: string; count: number }[] = []
      let matched = 0
      let llmTotal = 0
      let gtTotal = 0

      for (const count of llmMap.values()) llmTotal += count
      for (const count of gtMap.values()) gtTotal += count

      for (const size of allSizes) {
        const llmCount = llmMap.get(size) || 0
        const gtCount = gtMap.get(size) || 0
        matched += Math.min(llmCount, gtCount)
        if (gtCount > llmCount) missing.push({ size, count: gtCount - llmCount })
        if (llmCount > gtCount) extra.push({ size, count: llmCount - gtCount })
      }

      const sortItems = (items: { size: string; count: number }[]) =>
        items.sort((a, b) => Number(b.size) - Number(a.size))
      sortItems(missing)
      sortItems(extra)

      const denominator = Math.max(gtTotal, llmTotal)
      if (!denominator) {
        return { matched: 0, denominator: 0, rate: 0, missing, extra, status: 'empty' }
      }
      const rate = matched / denominator
      return {
        matched,
        denominator,
        rate,
        missing,
        extra,
        status: missing.length || extra.length ? 'mismatch' : 'match',
      }
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
      recordNoteDraft.value = rec?.note || ''
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
      allRecords, filteredRecords, tableColumns, resizableColumns,
      accuracyMode, getAccuracyValue, fieldMatchStats, follicleAverageStats, getFieldColumn,
      fieldColumns, fieldAttributionRows, filteredFieldAttributionRows, fieldAttributionColumns,
      attributionOverallStats, attributionFieldStats, attributionLevelOptions, attributionErrorTypeOptions,
      attributionKeyword, attributionFieldFilter, attributionStatusFilter, attributionLevelFilter, attributionErrorTypeFilter,
      attributionOnlyMarked, attributionOnlyFollicle,
      recordNoteDraft, recordNoteSaving, saveRecordNote,
      asrModels, asrModelId, asrRunning, asrProgress, runAsr,
      asrResultByModelId, currentAsrStatus, selectedAsrResult,
      llmModels, llmModelId, llmRunning, llmResult: currentLlmResult, currentLlmResult, llmPrompt, runLlm, compareField, formatRawJson,
      structured, llmDisplayText,
      selectBatch, openDetail, closeDrawer, onRowClick, formatDate, formatShortDateTime, formatFollicles,
      getLlmStatusColor, getLlmStatusText, getPromptTemplateNameById, formatAccuracy, getMatchStatus, matchTagColor, matchTagText, fieldStatusDisplayText,
      fieldStatusTagColor, isFollicleGroup, follicleMismatchLines,
      getFollicleRateColumn, follicleRateDisplayText, follicleRateTagColor,
      getListAsrStatusColor, getListAsrStatusText,
      getAsrModelStatusColor, getAsrModelStatusText, selectAsrModel,
      ScanOutlined, RobotOutlined, CheckCircleOutlined, CloseCircleOutlined, SettingOutlined, PlusOutlined, EyeOutlined, EditOutlined,
      promptTemplates, selectedTemplateId, showTemplateModal, showLlmDetailModal, templateTab, llmTab,
      batchAsrModelId, batchLlmModelId, batchTemplateId, batchRunning, batchMode, batchProgress, batchFailures, onBatchTemplateChange, runBatch,
      templateLoading, templateSaving, templateForm, templatePreviewHtml, showClearConfirm, clearing,
      onTemplateChange, selectTemplate, createNewTemplate, viewLlmHistory, setLlmAsCurrent, exportCurrentLlmHistory, exportLatestLlmForFilteredRecords, confirmClearLlmHistory, applyTemplateToCurrent, resetTemplateForm, saveTemplate, deleteTemplate,
      asrResultsAll, llmHistory,
      // 卵泡逐项对比
      normalizedLlmStructured, rightFollCompare, leftFollCompare, rightGtFolls, leftGtFolls, gtFollClass, detailGroupTextColor,
      // 真实 B 超结果编辑
      showBUltraModal, bUltraSaving, bUltraForm, openEditBUltra, saveBUltraResult,
      // 字段专项对比弹窗
      compareModalOpen, compareModalRecord, compareModalGroupKey, compareModalGroupTitle, compareModalMarkRefreshKey,
      getFieldCompareRows, openFieldCompare, getFieldReviewMark, onFieldMarkSaved, onFieldMarkCleared,
      // 人工标记
      markSaving, markClearing, markForm, markReasonOptions, handleSaveMark, handleClearMark,
    }
  },
})
</script>

<style scoped>
.page-container {
  width: 100%;
  max-width: none;
  box-sizing: border-box;
}
.page-container :deep(.ant-card),
.page-container :deep(.ant-card-body),
.page-container :deep(.ant-table-wrapper),
.page-container :deep(.ant-spin-nested-loading),
.page-container :deep(.ant-spin-container),
.page-container :deep(.ant-table) {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
}
.batch-filter {
  flex: 1;
  min-width: 0;
}
.record-search {
  width: 320px;
  flex: 0 0 320px;
}
.batch-action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  flex-wrap: wrap;
}
.batch-select {
  flex: 1 1 220px;
  min-width: 180px;
}
.batch-buttons {
  flex: 2 1 420px;
  min-width: 280px;
}
.table-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-label {
  color: #666;
  font-size: 12px;
}
.data-tabs {
  margin-top: 8px;
}
.attribution-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}
.attribution-stat-card {
  flex: 1 1 160px;
  min-width: 160px;
}
.stat-label {
  color: #666;
  font-size: 12px;
}
.stat-value {
  margin-top: 4px;
  color: #262626;
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
}
.stat-value.success {
  color: #52c41a;
}
.stat-value.danger {
  color: #ff4d4f;
}
.stat-value.warning {
  color: #fa8c16;
}
.stat-sub {
  margin-top: 4px;
  color: #999;
  font-size: 12px;
}
.field-attribution-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.attribution-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.attribution-original {
  white-space: pre-wrap;
  word-break: break-word;
}
@media (max-width: 900px) {
  .filter-row {
    align-items: stretch;
    flex-direction: column;
  }
  .record-search {
    width: 100%;
    flex-basis: auto;
  }
}
.follicle-list { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.compare-value-cell { white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.5; }
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
.match-fields-cell { display: flex; flex-wrap: wrap; gap: 2px; }
.col-resize-handle {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  z-index: 1;
}
.col-resize-handle:hover {
  background: #1890ff;
  opacity: 0.3;
}
.match-tag-sm { font-size: 11px; padding: 0 4px; line-height: 18px; margin: 0; }
.match-tag-sm.clickable { cursor: pointer; transition: transform 0.1s; }
.match-tag-sm.clickable:hover { transform: scale(1.1); box-shadow: 0 0 4px rgba(0,0,0,0.2); }
.follicle-summary-cell {
  min-width: 92px;
  max-width: 170px;
  white-space: normal;
  text-align: left;
  line-height: 1.45;
}
.follicle-summary-main {
  font-weight: 600;
  text-align: center;
}
.follicle-summary-line {
  margin-top: 2px;
  word-break: break-all;
}
.llm-model-info { font-size: 12px; color: #666; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.llm-model-asr { color: #1890ff; }
.llm-model-sep { margin: 0 1px; }
.llm-model-prompt { color: #999; }
.remark-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}
</style>
