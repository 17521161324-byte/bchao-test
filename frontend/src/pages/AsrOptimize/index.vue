<template>
  <div class="asr-optimize-page">
    <a-card class="page-card">
      <template #title>
        <a-space direction="vertical" :size="2">
          <span>优化评估</span>
          <span class="sub-title">先比较 ASR A/B/C 转写文本，再基于当前选中的 ASR 方案执行提示词 + LLM 结构化验证</span>
        </a-space>
      </template>
      <div class="filter-bar">
        <a-space wrap>
          <span class="label">评估选择</span>
          <a-radio-group v-model:value="selectedDate" button-style="solid">
            <a-radio-button v-for="item in dateOptions" :key="item.value" :value="item.value">{{ item.label }}</a-radio-button>
          </a-radio-group>
          <a-input-search v-model:value="keyword" allow-clear style="width: 240px" placeholder="搜索病历号" />
          <span class="muted">当前筛选 {{ filteredRecords.length }} 条</span>
          <a-button @click="loadAll" :loading="loading">刷新</a-button>
          <a-button :disabled="!canExport" @click="exportExcel">导出 Excel</a-button>
          <a-button :disabled="!canExportFull" :loading="fullExporting" @click="exportFullExcel">导出当前指纹完整数据</a-button>
        </a-space>
      </div>

      <div class="asr-plan-grid">
        <a-card
          v-for="slot in asrSlots"
          :key="slot.key"
          size="small"
          class="asr-plan-card"
          :class="{ active: activeSlotKey === slot.key, 'no-model': !slot.model_id }"
          @click="activeSlotKey = slot.key"
        >
          <template #title>
            <a-space>
              <a-tag :color="slotTagColor(slot.key)">ASR {{ slot.key }}</a-tag>
              <span>{{ slot.title }}</span>
            </a-space>
          </template>
          <template #extra>
            <a-space size="small" @click.stop>
              <a-button size="small" @click="openHistoryModal(slot.key)">选历史方案</a-button>
              <a-button size="small" type="primary" ghost @click="openConfigModal(slot.key)">新增配置</a-button>
            </a-space>
          </template>
          <div class="slot-compact">
            <div class="slot-meta">
              <span><b>模型</b>：{{ slot.model_id ? getModelName(slot.model_id) : '未选择' }}</span>
              <span><b>接口</b>：{{ endpointModeText(slot.params.endpoint_mode || 'bigmodel_nostream') }}</span>
              <span><b>音频</b>：{{ audioModeText(slot.params.audio_input_mode || 'segments') }}</span>
              <span><b>平台热词</b>：{{ featureStatus(slot, 'boosting') }}</span>
              <span><b>请求上下文</b>：{{ featureStatus(slot, 'hotwords') }}</span>
              <span><b>状态</b>：{{ slotStats(slot).success }}/{{ filteredRecords.length }}，缺 {{ slotStats(slot).missing }}</span>
              <span><b>指纹</b>：{{ slotConfigHash(slot).slice(0, 10) }}</span>
            </div>
            <div class="slot-actions" @click.stop>
              <a-space wrap :size="6">
                <a-button size="small" type="primary" :disabled="!slot.model_id || asrRunning" :loading="asrRunning" @click.stop="runSlotAsr(slot.key, false)">补齐 ASR {{ slot.key }}</a-button>
                <a-button size="small" danger :disabled="!slot.model_id || asrRunning" :loading="asrRunning" @click.stop="runSlotAsr(slot.key, true)">重跑 ASR {{ slot.key }}</a-button>
              </a-space>
            </div>
          </div>
        </a-card>
      </div>

      <div v-if="asrRunning || asrLogs.length" class="asr-log-panel">
        <div class="asr-log-header">
          <a-space wrap>
            <span class="label">ASR 执行进度</span>
            <a-tag color="blue">{{ asrCompleted }}/{{ asrTotal }}</a-tag>
            <span class="muted" v-if="asrProgress">{{ asrProgress }}</span>
          </a-space>
          <a-button size="small" :disabled="asrRunning" @click="clearAsrLogs">清空日志</a-button>
        </div>
        <a-progress :percent="asrProgressPercent" :status="asrRunning ? 'active' : asrFailedCount ? 'exception' : 'success'" />
        <div class="asr-log-list">
          <div v-for="log in asrLogs" :key="log.id" class="asr-log-line" :class="log.level">
            <span class="asr-log-time">[{{ log.time }}]</span>
            <span>{{ log.message }}</span>
          </div>
        </div>
      </div>

      <a-tabs>
        <a-tab-pane key="asr" tab="ASR转写对比">
          <a-table
            :columns="asrCompareColumns"
            :data-source="asrCompareRows"
            :loading="loading || asrRunning"
            :pagination="asrComparePagination"
            :scroll="{ x: 'max-content' }"
            :row-selection="asrRowSelection"
            row-key="patient_id"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.dataIndex === 'a_text'">
                <div class="asr-text-cell">
                  <div class="asr-text-meta">
                    <a-tag :color="statusColor(record.a_status)">{{ statusText(record.a_status) }}</a-tag>
                    <a-tag :color="asrIntegrityColor(record.a_integrity)">{{ asrIntegrityText(record.a_integrity) }}</a-tag>
                    <a-tag v-if="record.same_config" color="warning">方案同配置</a-tag>
                    <span v-if="record.a_error" class="asr-error">{{ record.a_error }}</span>
                    <a-button
                      v-if="canRepairAsrResult(record, 'A')"
                      size="small"
                      type="link"
                      :loading="repairingAsrResultIds[record.a_result_id]"
                      @click.stop="repairMissingSegments(record, 'A')"
                    >补跑缺失段</a-button>
                  </div>
                  <div v-if="asrIntegrityNote(record.a_integrity)" class="asr-integrity-note">{{ asrIntegrityNote(record.a_integrity) }}</div>
                  <div v-if="record.a_text" class="asr-text-content">
                    <span
                      v-for="(segment, index) in record.a_segments"
                      :key="`a-${record.patient_id}-${index}`"
                      :class="{ 'asr-diff-segment': segment.changed }"
                    >{{ segment.text }}</span>
                  </div>
                  <div v-else class="muted">暂无文本</div>
                </div>
              </template>
              <template v-else-if="column.dataIndex === 'b_text'">
                <div class="asr-text-cell">
                  <div class="asr-text-meta">
                    <a-tag :color="statusColor(record.b_status)">{{ statusText(record.b_status) }}</a-tag>
                    <a-tag :color="asrIntegrityColor(record.b_integrity)">{{ asrIntegrityText(record.b_integrity) }}</a-tag>
                    <a-tag v-if="record.same_config" color="warning">方案同配置</a-tag>
                    <span v-if="record.b_error" class="asr-error">{{ record.b_error }}</span>
                    <a-button
                      v-if="canRepairAsrResult(record, 'B')"
                      size="small"
                      type="link"
                      :loading="repairingAsrResultIds[record.b_result_id]"
                      @click.stop="repairMissingSegments(record, 'B')"
                    >补跑缺失段</a-button>
                  </div>
                  <div v-if="asrIntegrityNote(record.b_integrity)" class="asr-integrity-note">{{ asrIntegrityNote(record.b_integrity) }}</div>
                  <div v-if="record.b_text" class="asr-text-content">
                    <span
                      v-for="(segment, index) in record.b_segments"
                      :key="`b-${record.patient_id}-${index}`"
                      :class="{ 'asr-diff-segment': segment.changed }"
                    >{{ segment.text }}</span>
                  </div>
                  <div v-else class="muted">暂无文本</div>
                </div>
              </template>
              <template v-else-if="column.dataIndex === 'c_text'">
                <div class="asr-text-cell">
                  <div class="asr-text-meta">
                    <a-tag :color="statusColor(record.c_status)">{{ statusText(record.c_status) }}</a-tag>
                    <a-tag :color="asrIntegrityColor(record.c_integrity)">{{ asrIntegrityText(record.c_integrity) }}</a-tag>
                    <a-tag v-if="record.same_config" color="warning">方案同配置</a-tag>
                    <span v-if="record.c_error" class="asr-error">{{ record.c_error }}</span>
                    <a-button
                      v-if="canRepairAsrResult(record, 'C')"
                      size="small"
                      type="link"
                      :loading="repairingAsrResultIds[record.c_result_id]"
                      @click.stop="repairMissingSegments(record, 'C')"
                    >补跑缺失段</a-button>
                  </div>
                  <div v-if="asrIntegrityNote(record.c_integrity)" class="asr-integrity-note">{{ asrIntegrityNote(record.c_integrity) }}</div>
                  <div v-if="record.c_text" class="asr-text-content">
                    <span
                      v-for="(segment, index) in record.c_segments"
                      :key="`c-${record.patient_id}-${index}`"
                      :class="{ 'asr-diff-segment': segment.changed }"
                    >{{ segment.text }}</span>
                  </div>
                  <div v-else class="muted">暂无文本</div>
                </div>
              </template>
              <template v-else-if="column.dataIndex === 'action'">
                <a-button type="link" size="small" @click="openAsrDetail(record)">详情</a-button>
              </template>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="history" tab="ASR历史对比">
          <div class="history-layout">
            <aside class="history-patient-panel">
              <div class="history-patient-header">
                <div class="label">患者列表</div>
                <div class="muted">{{ historyPatientSummaries.length }} 条</div>
              </div>
              <a-empty v-if="!historyPatientSummaries.length" description="暂无检查记录" />
              <div v-else class="history-patient-list">
                <div
                  v-for="item in historyPatientSummaries"
                  :key="item.id"
                  class="history-patient-item"
                  :class="{ active: selectedHistoryPatientId === item.id }"
                  @click="selectHistoryPatient(item.id)"
                >
                  <div class="history-patient-main">
                    <span class="history-record-id">{{ item.record_id }}</span>
                    <span class="muted">{{ item.date }}</span>
                  </div>
                  <div class="history-patient-tags">
                    <a-tag color="blue">ASR {{ item.total }}</a-tag>
                    <a-tag v-if="item.hasReference" color="purple">标准</a-tag>
                    <a-tag v-if="item.complete" color="green">完整 {{ item.complete }}</a-tag>
                    <a-tag v-if="item.empty" color="blue">空段 {{ item.empty }}</a-tag>
                    <a-tag v-if="item.partial" color="orange">部分 {{ item.partial }}</a-tag>
                    <a-tag v-if="item.failed" color="red">失败 {{ item.failed }}</a-tag>
                  </div>
                  <div class="history-patient-models">{{ item.modelSummary || '暂无 ASR' }}</div>
                </div>
              </div>
            </aside>

            <section class="history-content-panel">
              <div class="history-toolbar">
                <a-space wrap>
                  <span class="label">{{ selectedHistoryRecord ? `${selectedHistoryRecord.record_id} · ${selectedHistoryRecord.date}` : '未选择检查记录' }}</span>
                  <span class="label">ASR模型</span>
                  <a-select v-model:value="historyModelFilter" allow-clear style="width: 180px" :options="historyModelFilterOptions" placeholder="全部模型" />
                  <span class="label">来源</span>
                  <a-select v-model:value="historySourceFilter" allow-clear style="width: 150px" :options="historySourceOptions" placeholder="全部来源" />
                  <span class="label">状态</span>
                  <a-select v-model:value="historyIntegrityFilter" allow-clear style="width: 170px" :options="historyIntegrityOptions" placeholder="全部状态" />
                  <span class="label">音频</span>
                  <a-select v-model:value="historyAudioModeFilter" allow-clear style="width: 150px" :options="historyAudioModeOptions" placeholder="全部音频模式" />
                  <span class="muted">共 {{ filteredHistoryAsrResults.length }} 条，已选 {{ selectedHistoryResultIds.length }}/2</span>
                </a-space>
              </div>

              <a-empty v-if="!selectedHistoryPatientId" description="请从左侧选择一条检查记录" />
              <a-empty v-else-if="!filteredHistoryAsrResults.length" description="当前筛选下暂无 ASR 历史记录" />
              <template v-else>
                <a-card size="small" class="reference-asr-panel">
                  <div class="reference-asr-header">
                    <a-space wrap>
                      <a-tag :color="selectedHistoryReference ? 'purple' : 'default'">标准 ASR</a-tag>
                      <span v-if="selectedHistoryReference">
                        已保存 · {{ selectedHistoryReference.base_asr_model_name || '未知底稿' }} · {{ selectedHistoryReference.reference_text.length }} 字
                      </span>
                      <span v-else class="muted">当前检查记录尚未建立人工校准 ASR，可从下方任意历史 ASR 设为底稿后编辑保存。</span>
                    </a-space>
                    <a-button
                      v-if="selectedHistoryReference"
                      size="small"
                      @click.stop="openReferenceEditor()"
                    >编辑标准文本</a-button>
                  </div>
                  <div v-if="selectedHistoryReference" class="reference-asr-text">
                    <span
                      v-for="(segment, index) in referenceDisplaySegments(selectedHistoryReference)"
                      :key="`reference-display-${index}`"
                      :class="referenceAnnotationClass(segment.type)"
                      :title="segment.note || ''"
                    >{{ segment.text }}</span>
                  </div>
                  <div v-if="selectedHistoryReference?.note" class="reference-asr-note">备注：{{ selectedHistoryReference.note }}</div>
                </a-card>

                <div class="history-card-grid">
                  <a-card
                    v-for="item in filteredHistoryAsrResults"
                    :key="item.id"
                    size="small"
                    class="history-asr-card"
                    :class="{ selected: selectedHistoryResultIds.includes(item.id) }"
                    @click="toggleHistoryResultSelection(item.id)"
                  >
                    <template #title>
                      <a-space wrap>
                        <a-checkbox :checked="selectedHistoryResultIds.includes(item.id)" @click.stop @change="toggleHistoryResultSelection(item.id)" />
                        <span>{{ historyResultTitle(item) }}</span>
                      </a-space>
                    </template>
                    <template #extra>
                      <a-space size="small">
                        <a-tag :color="statusColor(historyResultStatus(item))">{{ statusText(historyResultStatus(item)) }}</a-tag>
                        <a-tag :color="asrIntegrityColor(historyResultIntegrity(item))">{{ asrIntegrityText(historyResultIntegrity(item)) }}</a-tag>
                        <a-button size="small" type="link" @click.stop="openReferenceEditor(item)">设为标准底稿</a-button>
                      </a-space>
                    </template>
                    <div class="history-asr-meta">
                      <span><b>来源</b>：{{ sourceText(item.source) }}</span>
                      <span><b>音频</b>：{{ audioModeText(historyResultParams(item).audio_input_mode || historyResultParams(item).recognition_mode || 'segments') }}</span>
                      <span><b>时间</b>：{{ shortDateTime(item.created_at) }}</span>
                      <span><b>字数</b>：{{ asrTextFromResult(item).length }}</span>
                      <span><b>数字</b>：{{ extractNumbers(asrTextFromResult(item)).length }}</span>
                      <span v-if="item.config_hash"><b>指纹</b>：{{ item.config_hash.slice(0, 10) }}</span>
                    </div>
                    <div v-if="asrIntegrityNote(historyResultIntegrity(item))" class="asr-integrity-note">{{ asrIntegrityNote(historyResultIntegrity(item)) }}</div>
                    <div class="history-asr-text">{{ asrTextFromResult(item) || '暂无文本' }}</div>
                    <div v-if="item.error_message" class="asr-error history-error">{{ item.error_message }}</div>
                  </a-card>
                </div>

                <a-card v-if="historyComparePair.length === 2" size="small" class="history-compare-panel" title="选中结果差异对比">
                  <div class="history-compare-summary">
                    <a-tag color="blue">文本长度 {{ asrTextFromResult(historyComparePair[0]).length }} / {{ asrTextFromResult(historyComparePair[1]).length }}</a-tag>
                    <a-tag color="purple">数字数量 {{ extractNumbers(asrTextFromResult(historyComparePair[0])).length }} / {{ extractNumbers(asrTextFromResult(historyComparePair[1])).length }}</a-tag>
                    <a-tag :color="historyCompareChanged ? 'orange' : 'green'">{{ historyCompareChanged ? '有差异' : '完全一致' }}</a-tag>
                  </div>
                  <div class="history-compare-grid">
                    <div class="history-compare-text">
                      <div class="history-compare-title">{{ historyResultTitle(historyComparePair[0]) }}</div>
                      <div class="asr-text-content">
                        <span
                          v-for="(segment, index) in historyCompareSegments.a"
                          :key="`history-a-${index}`"
                          :class="{ 'asr-diff-segment': segment.changed }"
                        >{{ segment.text }}</span>
                      </div>
                    </div>
                    <div class="history-compare-text">
                      <div class="history-compare-title">{{ historyResultTitle(historyComparePair[1]) }}</div>
                      <div class="asr-text-content">
                        <span
                          v-for="(segment, index) in historyCompareSegments.b"
                          :key="`history-b-${index}`"
                          :class="{ 'asr-diff-segment': segment.changed }"
                        >{{ segment.text }}</span>
                      </div>
                    </div>
                  </div>
                </a-card>

                <a-card v-if="referenceCompareTarget" size="small" class="history-compare-panel" title="与标准 ASR 对比">
                  <div class="history-compare-summary">
                    <a-tag color="purple">标准 {{ selectedHistoryReference?.reference_text.length || 0 }} 字</a-tag>
                    <a-tag color="blue">选中 {{ asrTextFromResult(referenceCompareTarget).length }} 字</a-tag>
                    <a-tag :color="referenceCompareChanged ? 'orange' : 'green'">{{ referenceCompareChanged ? '有差异' : '完全一致' }}</a-tag>
                    <span class="muted">选择任意一条 ASR 历史记录后，会自动与标准文本对比。</span>
                  </div>
                  <div class="history-compare-grid">
                    <div class="history-compare-text">
                      <div class="history-compare-title">标准 ASR（人工校准）</div>
                      <div class="asr-text-content">
                        <span
                          v-for="(segment, index) in referenceCompareSegments.a"
                          :key="`reference-a-${index}`"
                          :class="{ 'asr-diff-segment': segment.changed }"
                        >{{ segment.text }}</span>
                      </div>
                    </div>
                    <div class="history-compare-text">
                      <div class="history-compare-title">{{ historyResultTitle(referenceCompareTarget) }}</div>
                      <div class="asr-text-content">
                        <span
                          v-for="(segment, index) in referenceCompareSegments.b"
                          :key="`reference-b-${index}`"
                          :class="{ 'asr-diff-segment': segment.changed }"
                        >{{ segment.text }}</span>
                      </div>
                    </div>
                  </div>
                </a-card>
              </template>
            </section>
          </div>
        </a-tab-pane>

        <a-tab-pane key="data" tab="数据对比">
          <div class="structured-toolbar">
            <a-space wrap>
              <span class="label">当前 ASR</span>
              <span class="muted">{{ activeSlotLabel }}</span>
              <span class="label">提示词</span>
              <a-select v-model:value="selectedTemplateId" style="width: 220px" :options="templateOptions" placeholder="选择提示词" />
              <span class="label">LLM</span>
              <a-select v-model:value="selectedLlmModelId" style="width: 180px" :options="llmOptions" placeholder="选择 LLM" />
              <a-button type="primary" :disabled="!canRunLlm" :loading="llmRunning" @click="runBatchLlm">批量重新跑 LLM</a-button>
              <span class="muted" v-if="llmProgress">{{ llmProgress }}</span>
            </a-space>
          </div>

          <div class="field-stats-row">
            <span class="label">字段成功率：</span>
            <a-tag v-for="stat in structuredFieldStats" :key="stat.key" :color="stat.rate >= 0.9 ? 'green' : stat.rate >= 0.7 ? 'orange' : 'red'">
              {{ stat.label }} {{ stat.matched }}/{{ stat.total }} · {{ stat.total ? (stat.rate * 100).toFixed(1) : '-' }}%
            </a-tag>
            <span class="label">卵泡明细：</span>
            <a-tag v-for="stat in follicleDetailStats" :key="stat.key" :color="stat.rate >= 0.9 ? 'green' : stat.rate >= 0.7 ? 'orange' : 'red'">
              {{ stat.label }} 平均{{ stat.total ? (stat.rate * 100).toFixed(1) : '-' }}% · 样本{{ stat.total }}
            </a-tag>
          </div>

          <div class="chart-panel">
            <div class="chart-toolbar">
              <a-space wrap>
                <span class="label">图形化对比</span>
                <span class="muted">提示词 + LLM 组合</span>
                <span class="label">LLM筛选</span>
                <a-select
                  v-model:value="chartLlmModelId"
                  allow-clear
                  style="width: 190px"
                  :options="chartLlmOptions"
                  placeholder="全部 LLM"
                />
                <span class="muted">
                  当前 ASR：{{ activeSlotLabel }}；{{ analysisChartGroups.length }} 组 / {{ analysisLlmRows.length }} 条最新结果
                </span>
              </a-space>
            </div>
            <a-empty v-if="!analysisChartGroups.length" description="暂无可用于图形化对比的 LLM 结构化结果" />
            <template v-else>
              <div class="bar-chart">
                <div class="bar-legend">
                  <span><i class="legend-dot overall"></i>字段整体成功率</span>
                  <span><i class="legend-dot follicle"></i>左右卵泡明细平均</span>
                </div>
                <div v-for="group in analysisChartGroups" :key="group.key" class="bar-row">
                  <div class="bar-name" :title="group.label">{{ group.label }}</div>
                  <div class="bar-track">
                    <div class="bar-fill overall" :style="{ width: percentWidth(group.overallRate) }"></div>
                  </div>
                  <div class="bar-value">{{ formatPercent(group.overallRate) }}</div>
                  <div class="bar-track">
                    <div class="bar-fill follicle" :style="{ width: percentWidth(group.follicleRate) }"></div>
                  </div>
                  <div class="bar-value">{{ formatPercent(group.follicleRate) }}</div>
                  <div class="bar-count">样本 {{ group.sampleCount }}</div>
                </div>
              </div>

              <div class="heatmap-wrap">
                <div class="heatmap-title">字段成功率热力图</div>
                <div class="heatmap-grid" :style="{ gridTemplateColumns: heatmapGridColumns }">
                  <div class="heatmap-head sticky-field">字段</div>
                  <div v-for="group in analysisChartGroups" :key="`head-${group.key}`" class="heatmap-head group-head" :title="group.label">
                    {{ group.shortLabel }}
                  </div>
                  <template v-for="field in chartHeatmapFields" :key="field.key">
                    <div class="heatmap-field">{{ field.label }}</div>
                    <div
                      v-for="group in analysisChartGroups"
                      :key="`${field.key}-${group.key}`"
                      class="heatmap-cell"
                      :style="{ background: heatmapColor(group.fieldRates[field.key]?.rate) }"
                      :title="`${group.label} / ${field.label}：${formatPercent(group.fieldRates[field.key]?.rate)}，${group.fieldRates[field.key]?.matched}/${group.fieldRates[field.key]?.total}`"
                    >
                      <span>{{ formatPercent(group.fieldRates[field.key]?.rate) }}</span>
                      <small>{{ group.fieldRates[field.key]?.matched }}/{{ group.fieldRates[field.key]?.total }}</small>
                    </div>
                  </template>
                </div>
              </div>
            </template>
          </div>

          <div class="prompt-run-switch">
            <a-space wrap>
              <span class="label">已跑组合：</span>
              <template v-if="usedLlmRunOptions.length">
                <a-radio-group v-model:value="selectedLlmRunKey" button-style="solid">
                  <a-radio-button v-for="item in usedLlmRunOptions" :key="item.value" :value="item.value">
                    {{ item.label }}（{{ item.count }}）
                  </a-radio-button>
                </a-radio-group>
              </template>
              <span v-else class="muted">当前 ASR 方案下暂无已跑 LLM 结果</span>
            </a-space>
          </div>

          <a-tabs>
            <a-tab-pane key="structured" tab="结构化结果">
          <a-table
            :columns="structuredColumns"
            :data-source="structuredRows"
            :loading="loading || llmRunning"
            :pagination="structuredPagination"
            :scroll="{ x: 'max-content' }"
            row-key="patient_id"
            size="small"
          >
            <template #bodyCell="{ column, record }">
                  <template v-if="column.dataIndex === 'accuracy'">
                    {{ formatPercent(record.accuracy) }}
                  </template>
              <template v-else-if="isStructuredField(column.dataIndex)">
                <div class="field-cell" @click="openFieldDetail(record, column.dataIndex)">
                  <a-tag :color="fieldDisplayColor(record, column.dataIndex)" class="match-tag">
                    {{ fieldDisplayText(record, column.dataIndex) }}
                  </a-tag>
                  <div v-if="getFieldDisplayNote(record, column.dataIndex)" class="field-note">{{ getFieldDisplayNote(record, column.dataIndex) }}</div>
                </div>
              </template>
              <template v-else-if="column.dataIndex === 'action'">
                <a-button type="link" size="small" @click="openStructuredDetail(record)">详情</a-button>
              </template>
            </template>
          </a-table>
            </a-tab-pane>

            <a-tab-pane key="attribution" tab="逐字段归因">
          <div class="attribution-stats">
            <a-card size="small" class="attribution-stat-card">
              <div class="stat-label">字段总数</div>
              <div class="stat-value">{{ attributionOverallStats.total }}</div>
            </a-card>
            <a-card size="small" class="attribution-stat-card">
              <div class="stat-label">归因正确率</div>
              <div class="stat-value success">{{ formatPercent(attributionOverallStats.accuracy) }}</div>
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
          <div class="attribution-filters">
            <a-select v-model:value="attributionFieldFilter" placeholder="字段" allow-clear style="width: 150px">
              <a-select-option v-for="field in fieldColumns" :key="field.key" :value="field.key">{{ field.label }}</a-select-option>
            </a-select>
            <a-select v-model:value="attributionStatusFilter" placeholder="状态" allow-clear style="width: 130px">
              <a-select-option value="正确">正确</a-select-option>
              <a-select-option value="错误">错误</a-select-option>
              <a-select-option value="排除">排除</a-select-option>
              <a-select-option value="异常">异常</a-select-option>
              <a-select-option value="未提取">未提取</a-select-option>
            </a-select>
            <a-checkbox v-model:checked="attributionOnlyMarked">只看人工标记</a-checkbox>
            <a-button size="small" @click="resetAttributionFilters">清空筛选</a-button>
            <span class="muted">标记绑定当前 LLM 历史结果，不影响数据管理旧标记</span>
          </div>
          <a-table
            :columns="attributionColumns"
            :data-source="filteredAttributionRows"
            :pagination="attributionPagination"
            :scroll="{ x: 'max-content' }"
            row-key="key"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.dataIndex === 'status'">
                <a-tag :color="attributionStatusColor(record.status)">{{ record.status }}</a-tag>
              </template>
              <template v-else-if="column.dataIndex === 'reason'">
                <div class="attribution-reason">{{ record.reason }}</div>
              </template>
              <template v-else-if="column.dataIndex === 'action'">
                <a-space size="small">
                  <a-button size="small" type="link" @click="openAttributionMark(record)">标记</a-button>
                  <a-button v-if="record.has_mark" size="small" type="link" danger @click="clearAttributionMark(record)">清除</a-button>
                </a-space>
              </template>
            </template>
          </a-table>
            </a-tab-pane>
          </a-tabs>
        </a-tab-pane>
      </a-tabs>
    </a-card>

    <a-modal
      v-model:open="historyModalOpen"
      :title="`选择历史方案 · ASR ${editingSlotKey}`"
      width="860px"
      :footer="null"
    >
      <div class="history-filter">
        <span class="label">ASR 模型筛选</span>
        <a-radio-group v-model:value="selectedHistoryAsrModelId" button-style="solid">
          <a-radio-button :value="undefined">全部</a-radio-button>
          <a-radio-button v-for="item in historyAsrModelOptions" :key="item.value" :value="item.value">{{ item.label }}</a-radio-button>
        </a-radio-group>
      </div>

      <a-divider orientation="left">选择历史/已保存配置方案</a-divider>
      <div v-if="filteredAsrPlanList.length" class="plan-select-grid">
        <a-card
          v-for="plan in filteredAsrPlanList"
          :key="plan.id"
          size="small"
          class="plan-select-card"
          :class="{ active: selectedHistoryPlanId === plan.id }"
          @click="selectedHistoryPlanId = plan.id"
        >
          <template #title>
            <a-space>
              <a-tag :color="plan.source === 'custom' || plan.source === 'saved' ? 'blue' : 'default'">{{ plan.source === 'history' ? '历史' : '已保存' }}</a-tag>
              <span>{{ planDisplayName(plan) }}</span>
            </a-space>
          </template>
          <template #extra>
              <a-space size="small" @click.stop>
              <a-button size="small" @click.stop="editHistoryPlan(plan)">编辑</a-button>
                <a-popconfirm
                  title="确认删除该历史配置方案？会删除该配置对应的优化评估 ASR/LLM 历史结果，不影响普通数据。"
                ok-text="删除"
                cancel-text="取消"
                @confirm.stop="deleteSavedPlan(plan)"
              >
                <a-button size="small" danger @click.stop>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
          <div class="plan-card-meta">
            <span><b>模型</b>：{{ plan.model_id ? getModelName(plan.model_id) : '未知模型' }}</span>
            <span><b>音频</b>：{{ audioModeText(plan.params?.audio_input_mode || 'segments') }}</span>
            <span><b>热词</b>：{{ planFeatureStatus(plan, 'hotwords') }}</span>
            <span><b>结果</b>：{{ planStats(plan).success }}/{{ filteredRecords.length }}，缺 {{ planStats(plan).missing }}</span>
          </div>
          <div class="plan-card-actions">
            <a-button type="primary" size="small" @click.stop="applyPlanToSlot(plan)">使用该方案</a-button>
          </div>
        </a-card>
      </div>
      <a-empty v-else description="当前筛选下暂无可选配置方案" />
      <div class="form-tip">使用历史方案会保留原 config_hash，已有识别结果会立即匹配显示；缺失记录需手动点“补齐”。</div>

      <template v-if="selectedHistoryPlan">
        <a-divider orientation="left">方案内容预览</a-divider>
        <a-descriptions bordered size="small" :column="2">
          <a-descriptions-item label="方案名称">{{ planDisplayName(selectedHistoryPlan) }}</a-descriptions-item>
          <a-descriptions-item label="来源">{{ selectedHistoryPlan.source === 'history' ? '历史识别结果' : '已保存配置' }}</a-descriptions-item>
          <a-descriptions-item label="ASR 模型">{{ selectedHistoryPlan.model_id ? getModelName(selectedHistoryPlan.model_id) : '未知模型' }}</a-descriptions-item>
          <a-descriptions-item label="已有结果">{{ planStats(selectedHistoryPlan).success }}/{{ filteredRecords.length }}，缺 {{ planStats(selectedHistoryPlan).missing }}</a-descriptions-item>
          <a-descriptions-item label="接口模式">{{ endpointModeText(selectedHistoryPlan.params?.endpoint_mode || 'bigmodel_nostream') }}</a-descriptions-item>
          <a-descriptions-item label="音频读取">{{ audioModeText(selectedHistoryPlan.params?.audio_input_mode || 'segments') }}</a-descriptions-item>
          <a-descriptions-item label="平台热词">{{ planFeatureStatus(selectedHistoryPlan, 'boosting') }}</a-descriptions-item>
          <a-descriptions-item label="替换词表">{{ planFeatureStatus(selectedHistoryPlan, 'correct') }}</a-descriptions-item>
          <a-descriptions-item label="请求上下文">{{ planFeatureStatus(selectedHistoryPlan, 'hotwords') }}</a-descriptions-item>
          <a-descriptions-item label="配置指纹">{{ getPlanHash(selectedHistoryPlan).slice(0, 12) }}</a-descriptions-item>
        </a-descriptions>
        <a-divider orientation="left">热词 / 上下文</a-divider>
        <div class="plan-preview-grid">
          <a-card size="small" title="请求上下文 · 热词列表">
            <pre class="plan-preview-text">{{ formatHotwords(selectedHistoryPlan.params?.hotwords) }}</pre>
          </a-card>
          <a-card size="small" title="请求上下文 · 业务上下文">
            <pre class="plan-preview-text">{{ selectedHistoryPlan.params?.context_text || '未配置' }}</pre>
          </a-card>
        </div>
      </template>
      <a-empty v-else description="请选择一个历史方案，下面会展示该方案的完整配置内容" />
    </a-modal>

    <a-modal
      v-model:open="configModalOpen"
      :title="configModalTitle"
      width="760px"
      :ok-text="editingPlan ? '保存历史方案' : '保存配置'"
      cancel-text="取消"
      @ok="saveSlotConfig"
    >
      <a-form layout="vertical">
        <a-form-item label="启用 ASR 模型" required>
          <a-radio-group v-model:value="slotForm.model_id" button-style="solid" @change="onSlotModelChange">
            <a-radio-button v-for="model in activeAsrModels" :key="model.id" :value="model.id">{{ model.name }}</a-radio-button>
          </a-radio-group>
          <div v-if="!activeAsrModels.length" class="form-tip">暂无启用的 ASR 模型，请先到模型配置中启用。</div>
        </a-form-item>
        <a-form-item label="显示名称">
          <a-input v-model:value="slotForm.title" placeholder="例如：基线 / 热词方案" />
        </a-form-item>
        <template v-if="selectedSlotModel">
          <a-alert type="info" show-icon style="margin-bottom: 12px" :message="`当前模型：${selectedSlotModel.name} / ${providerLabel(selectedSlotModel.provider)}。配置默认继承模型配置，可在本方案中临时覆盖。`" />
          <a-form-item label="音频读取方式">
            <a-radio-group v-model:value="slotForm.params.audio_input_mode">
              <a-radio value="segments">原始分段</a-radio>
              <a-radio value="grouped">连续分组合并</a-radio>
              <a-radio value="merged">整段合并音频</a-radio>
            </a-radio-group>
          </a-form-item>

          <a-card v-if="isMimoSlotModel" size="small" title="MiMo ASR 专属配置" class="provider-card">
            <a-form-item label="识别语言">
              <a-select v-model:value="slotForm.params.language">
                <a-select-option value="auto">auto（自动识别）</a-select-option>
                <a-select-option value="zh">zh（中文）</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="启用 stream 返回">
              <a-switch v-model:checked="slotForm.params.stream" />
              <div class="form-tip">MiMo 的 stream 是完整音频上传后的响应流式返回。</div>
            </a-form-item>
            <a-space class="switch-row" wrap>
              <span>连续分组大小</span><a-input-number v-model:value="slotForm.params.merge_group_size" :min="1" :max="10" style="width: 120px" />
              <span>Base64 上限(MB)</span><a-input-number v-model:value="slotForm.params.max_base64_mb" :min="1" :max="10" :step="0.1" style="width: 120px" />
            </a-space>
          </a-card>

          <a-card v-else-if="isVolcengineSlotModel" size="small" title="豆包 ASR 专属配置" class="provider-card">
            <a-form-item label="接口模式">
              <a-radio-group v-model:value="slotForm.params.endpoint_mode">
                <a-radio value="bigmodel_nostream">流式输入 nostream（准确率优先）</a-radio>
                <a-radio value="bigmodel">双向流式</a-radio>
                <a-radio value="bigmodel_async">双向流式优化版</a-radio>
              </a-radio-group>
            </a-form-item>
            <a-form-item label="结果返回类型">
              <a-select v-model:value="slotForm.params.result_type">
                <a-select-option value="full">full（全量结果，推荐）</a-select-option>
                <a-select-option value="single">single（单次结果）</a-select-option>
              </a-select>
            </a-form-item>
            <a-space class="switch-row" wrap>
              <span>数字规整</span><a-switch v-model:checked="slotForm.params.enable_itn" />
              <span>标点</span><a-switch v-model:checked="slotForm.params.enable_punc" />
              <span>顺滑</span><a-switch v-model:checked="slotForm.params.enable_ddc" />
              <span>分句</span><a-switch v-model:checked="slotForm.params.show_utterances" />
              <span>二遍识别</span><a-switch v-model:checked="slotForm.params.enable_nonstream" />
            </a-space>
            <a-space class="switch-row" wrap>
              <span>判停(ms)</span><a-input-number v-model:value="slotForm.params.end_window_size" :min="200" :max="5000" style="width: 120px" />
              <span>语义切句(ms)</span><a-input-number v-model:value="slotForm.params.vad_segment_duration" :min="200" :max="10000" style="width: 120px" />
              <span>强制语音(ms)</span><a-input-number v-model:value="slotForm.params.force_to_speech_time" :min="1" :max="10000" style="width: 120px" />
            </a-space>
            <a-divider orientation="left">平台词表 / 请求上下文</a-divider>
            <a-space class="switch-row" wrap>
              <span>启用平台热词</span><a-switch v-model:checked="slotForm.params.use_boosting_table" />
              <span>启用替换词表</span><a-switch v-model:checked="slotForm.params.use_correct_table" />
              <span>启用请求上下文</span><a-switch v-model:checked="slotForm.params.use_context_hotwords" />
            </a-space>
            <a-form-item label="平台热词表 ID">
              <a-input v-model:value="slotForm.params.boosting_table_id" placeholder="可选，默认继承模型配置" />
            </a-form-item>
            <a-form-item label="平台替换词表 ID">
              <a-input v-model:value="slotForm.params.correct_table_id" placeholder="可选，默认继承模型配置" />
            </a-form-item>
            <a-form-item label="请求上下文模式">
              <a-radio-group v-model:value="slotForm.params.context_mode">
                <a-radio value="hotwords">热词列表</a-radio>
                <a-radio value="dialog_ctx">业务上下文</a-radio>
              </a-radio-group>
              <div class="form-tip">两种模式最终都写入豆包 request.corpus.context，同一次调用只会生效一种。</div>
            </a-form-item>
            <a-form-item v-if="slotForm.params.context_mode !== 'dialog_ctx'" label="请求上下文 · 热词列表">
              <a-textarea v-model:value="slotHotwordsText" :rows="5" placeholder="每行一个热词" />
            </a-form-item>
            <a-form-item v-else label="请求上下文 · 业务上下文">
              <a-textarea v-model:value="slotForm.params.context_text" :rows="4" placeholder="例如：当前录音为辅助生殖阴道B超卵泡监测..." />
            </a-form-item>
          </a-card>

          <a-card v-else size="small" :title="`${providerLabel(selectedSlotModel.provider)} ASR 配置`" class="provider-card">
            <a-empty description="该模型暂无优化评估专属参数，仅使用模型配置中的基础参数和上方音频读取方式。" />
          </a-card>
        </template>
        <a-empty v-else description="请先在上方选择一个已启用 ASR 模型，选择后才显示该模型对应配置。" />
      </a-form>
    </a-modal>

    <a-modal v-model:open="asrDetailOpen" width="1200px" title="ASR 转写对比详情" :footer="null">
      <template v-if="asrDetailRow">
        <a-row :gutter="16">
          <a-col :span="8">
            <a-divider orientation="left">ASR A</a-divider>
            <div class="detail-text">{{ asrDetailRow.a_text || asrDetailRow.a_error || '暂无文本' }}</div>
          </a-col>
          <a-col :span="8">
            <a-divider orientation="left">ASR B</a-divider>
            <div class="detail-text">{{ asrDetailRow.b_text || asrDetailRow.b_error || '暂无文本' }}</div>
          </a-col>
          <a-col :span="8">
            <a-divider orientation="left">ASR C</a-divider>
            <div class="detail-text">{{ asrDetailRow.c_text || asrDetailRow.c_error || '暂无文本' }}</div>
          </a-col>
        </a-row>
      </template>
    </a-modal>

    <ExamDetailDrawer
      :visible="examDetailVisible"
      :data="examDetailData"
      @close="examDetailVisible = false"
    />

    <a-drawer
      :open="structuredDetailOpen"
      placement="right"
      width="92vw"
      :title="`${structuredDetailRow?.record_id || ''} - 检查详情`"
      @close="structuredDetailOpen = false"
    >
      <template v-if="structuredDetailRow">
        <a-descriptions bordered size="small" :column="4" style="margin-bottom: 14px">
          <a-descriptions-item label="病历号">{{ structuredDetailRow.record_id }}</a-descriptions-item>
          <a-descriptions-item label="日期">{{ structuredDetailRow.date }}</a-descriptions-item>
          <a-descriptions-item label="ASR方案">{{ slotDisplayName(activeSlot) }}</a-descriptions-item>
          <a-descriptions-item label="准确率">{{ formatPercent(structuredDetailRow.accuracy) }}</a-descriptions-item>
          <a-descriptions-item label="ASR模型">{{ getActiveAsrResult(structuredDetailRow)?.model_name || getActiveAsrResult(structuredDetailRow)?.asr_model_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="提示词">{{ structuredDetailRow.llm?.prompt_template_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="LLM模型">{{ structuredDetailRow.llm?.model_name || structuredDetailRow.llm?.llm_model_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="录音">{{ structuredDetailRow.record?.segs?.length || 0 }} 段</a-descriptions-item>
        </a-descriptions>

        <template v-if="structuredDetailField">
          <a-row :gutter="14">
            <a-col :span="16">
              <a-card size="small" class="detail-section-card">
                <template #title>
                  <a-space>
                    <span>{{ getFieldLabel(structuredDetailField) }}专项对比</span>
                    <a-tag :color="fieldDisplayColor(structuredDetailRow, structuredDetailField)">
                      {{ fieldDisplayText(structuredDetailRow, structuredDetailField) }}
                    </a-tag>
                  </a-space>
                </template>
                <div v-if="structuredDetailRow.field_notes[structuredDetailField]" class="detail-warning">
                  {{ structuredDetailRow.field_notes[structuredDetailField] }}
                </div>
                <a-table
                  :data-source="getBusinessFieldCompareRows(structuredDetailRow, structuredDetailField)"
                  size="small"
                  row-key="key"
                  :pagination="false"
                  bordered
                >
                  <a-table-column title="字段" data-index="label" :width="120" />
                  <a-table-column title="匹配" :width="80" align="center">
                    <template #default="{ record }">
                      <a-tag :color="matchColor(record.status)">{{ matchText(record.status) }}</a-tag>
                    </template>
                  </a-table-column>
                  <a-table-column title="LLM结果">
                    <template #default="{ record }">
                      <div class="compare-value-cell" :class="{ mismatch: record.status === 'mismatch' }">{{ record.llmText }}</div>
                    </template>
                  </a-table-column>
                  <a-table-column title="真实值">
                    <template #default="{ record }">
                      <div class="compare-value-cell">{{ record.gtText }}</div>
                    </template>
                  </a-table-column>
                </a-table>
              </a-card>
              <a-card size="small" title="当前字段差异摘要" class="detail-section-card">
                <div class="field-diff-summary" :class="fieldDisplayColor(structuredDetailRow, structuredDetailField)">
                  {{ getFieldDifferenceSummary(structuredDetailRow, structuredDetailField) }}
                </div>
              </a-card>
            </a-col>
            <a-col :span="8">
              <a-card size="small" title="人工标记" class="detail-section-card">
                <template v-if="getStructuredDetailMark()">
                  <a-alert :type="getStructuredDetailMark()?.mark_type === 'exclude' ? 'warning' : 'error'" show-icon style="margin-bottom: 12px">
                    <template #message>
                      <a-space direction="vertical" style="width: 100%">
                        <div>
                          <strong>{{ getStructuredDetailMark()?.mark_type === 'exclude' ? '排除统计' : '异常说明，计入错误' }}</strong>
                          <a-button type="link" size="small" danger @click="clearStructuredDetailMark">清除标记</a-button>
                        </div>
                        <div v-if="getStructuredDetailMark()?.reason">原因：{{ getStructuredDetailMark()?.reason }}</div>
                        <div v-if="getStructuredDetailMark()?.note">备注：{{ getStructuredDetailMark()?.note }}</div>
                      </a-space>
                    </template>
                  </a-alert>
                </template>
                <a-empty v-else description="暂无人工标记" style="margin-bottom: 12px" />
                <a-form layout="vertical" size="small">
                  <a-form-item label="标记类型">
                    <a-select v-model:value="attributionMarkForm.mark_type">
                      <a-select-option value="exclude">排除统计</a-select-option>
                      <a-select-option value="mismatch_note">异常说明，计入错误</a-select-option>
                    </a-select>
                  </a-form-item>
                  <a-form-item label="原因">
                    <a-select v-model:value="attributionMarkForm.reason" allow-clear placeholder="选择原因">
                      <a-select-option v-for="reason in attributionReasonOptions" :key="reason" :value="reason">{{ reason }}</a-select-option>
                    </a-select>
                  </a-form-item>
                  <a-form-item label="备注">
                    <a-textarea v-model:value="attributionMarkForm.note" :rows="3" placeholder="补充说明，可为空" />
                  </a-form-item>
                  <a-button type="primary" block :loading="attributionMarkSaving" :disabled="!structuredDetailRow.llm?.id" @click="saveStructuredDetailMark">保存标记</a-button>
                </a-form>
              </a-card>
            </a-col>
          </a-row>
        </template>

        <template v-else>
          <a-row :gutter="14">
            <a-col :span="12">
              <a-card size="small" title="语音转写（ASR）" class="detail-section-card">
                <div class="text-box detail-transcript">{{ getActiveAsrResult(structuredDetailRow)?.full_transcript || '暂无 ASR 转写文本' }}</div>
              </a-card>
            </a-col>
            <a-col :span="12">
              <a-card size="small" title="LLM 总结" class="detail-section-card">
                <div class="detail-text">{{ structuredDetailRow.llm?.summary_text || structuredDetailRow.llm?.summary || '暂无总结' }}</div>
              </a-card>
            </a-col>
          </a-row>

          <a-card size="small" title="字段差异汇总" class="detail-section-card">
            <a-table
              :data-source="getMismatchBusinessCompareRows(structuredDetailRow)"
              size="small"
              row-key="key"
              :pagination="false"
              bordered
            >
              <a-table-column title="字段" data-index="label" :width="120" />
              <a-table-column title="LLM结果">
                <template #default="{ record }">
                  <div class="compare-value-cell mismatch">{{ record.llmText }}</div>
                </template>
              </a-table-column>
              <a-table-column title="真实值">
                <template #default="{ record }">
                  <div class="compare-value-cell">{{ record.gtText }}</div>
                </template>
              </a-table-column>
            </a-table>
            <a-empty v-if="!getMismatchBusinessCompareRows(structuredDetailRow).length" description="当前无字段差异" />
          </a-card>

          <a-row :gutter="14">
            <a-col :span="12">
              <a-card size="small" title="LLM 提取结果" class="detail-section-card">
                <a-table
                  :data-source="getAllBusinessCompareRows(structuredDetailRow)"
                  size="small"
                  row-key="key"
                  :pagination="false"
                  bordered
                >
                  <a-table-column title="字段" data-index="label" :width="120" />
                  <a-table-column title="匹配" :width="80" align="center">
                    <template #default="{ record }">
                      <a-tag :color="matchColor(record.status)">{{ matchText(record.status) }}</a-tag>
                    </template>
                  </a-table-column>
                  <a-table-column title="LLM结果">
                    <template #default="{ record }">
                      <div class="compare-value-cell" :class="{ mismatch: record.status === 'mismatch' }">{{ record.llmText }}</div>
                    </template>
                  </a-table-column>
                  <a-table-column title="真实值">
                    <template #default="{ record }">
                      <div class="compare-value-cell">{{ record.gtText }}</div>
                    </template>
                  </a-table-column>
                </a-table>
              </a-card>
            </a-col>
            <a-col :span="12">
              <a-card size="small" title="录音播放" class="detail-section-card">
                <AudioPlayer v-if="structuredDetailRow.record?.segs?.length" :segs="structuredDetailRow.record.segs" />
                <a-empty v-else description="暂无录音文件" />
              </a-card>
              <a-card size="small" title="录音分段明细" class="detail-section-card">
                <a-table
                  :data-source="getAudioSegmentRows(structuredDetailRow)"
                  size="small"
                  row-key="key"
                  :pagination="false"
                  bordered
                >
                  <a-table-column title="序号" data-index="seg_index" :width="80" />
                  <a-table-column title="文件" data-index="filename" />
                  <a-table-column title="时长" data-index="duration" :width="90" />
                  <a-table-column title="大小" data-index="file_size" :width="100" />
                </a-table>
                <a-empty v-if="!getAudioSegmentRows(structuredDetailRow).length" description="暂无录音分段" />
              </a-card>
            </a-col>
          </a-row>

          <a-collapse class="detail-section-card">
            <a-collapse-panel key="json" header="结构化 JSON / LLM 原始返回">
              <pre class="json-box">{{ JSON.stringify(structuredDetailRow.llm?.structured_result || structuredDetailRow.llm?.structured || {}, null, 2) }}</pre>
              <a-divider orientation="left">原始返回</a-divider>
              <pre class="json-box">{{ structuredDetailRow.llm?.raw_output || structuredDetailRow.llm?.raw_text || '暂无原始返回' }}</pre>
            </a-collapse-panel>
          </a-collapse>
        </template>
      </template>
    </a-drawer>

    <a-modal
      :open="fieldDetailOpen"
      :title="`${fieldDetailRow?.record_id || ''} - ${getFieldLabel(fieldDetailField)} 明细`"
      width="980px"
      :footer="null"
      @cancel="fieldDetailOpen = false"
      destroy-on-close
    >
      <template v-if="fieldDetailRow">
        <a-descriptions bordered size="small" :column="3" style="margin-bottom: 12px">
          <a-descriptions-item label="病历号">{{ fieldDetailRow.record_id }}</a-descriptions-item>
          <a-descriptions-item label="日期">{{ fieldDetailRow.date }}</a-descriptions-item>
          <a-descriptions-item label="字段">
            <a-tag :color="fieldDisplayColor(fieldDetailRow, fieldDetailField)">
              {{ getFieldLabel(fieldDetailField) }} · {{ fieldDisplayText(fieldDetailRow, fieldDetailField) }}
            </a-tag>
          </a-descriptions-item>
        </a-descriptions>

        <a-row :gutter="14">
          <a-col :span="15">
            <a-card size="small" title="当前字段差异" class="detail-section-card">
              <div class="field-diff-summary" :class="fieldDisplayColor(fieldDetailRow, fieldDetailField)">
                {{ getFieldDifferenceSummary(fieldDetailRow, fieldDetailField) }}
              </div>
            </a-card>
            <a-card size="small" title="字段专项对比" class="detail-section-card">
              <a-table
                :data-source="getBusinessFieldCompareRows(fieldDetailRow, fieldDetailField)"
                size="small"
                row-key="key"
                :pagination="false"
                bordered
              >
                <a-table-column title="字段" data-index="label" :width="120" />
                <a-table-column title="匹配" :width="80" align="center">
                  <template #default="{ record }">
                    <a-tag :color="matchColor(record.status)">{{ matchText(record.status) }}</a-tag>
                  </template>
                </a-table-column>
                <a-table-column title="LLM结果">
                  <template #default="{ record }">
                    <div class="compare-value-cell" :class="{ mismatch: record.status === 'mismatch' }">{{ record.llmText }}</div>
                  </template>
                </a-table-column>
                <a-table-column title="真实值">
                  <template #default="{ record }">
                    <div class="compare-value-cell">{{ record.gtText }}</div>
                  </template>
                </a-table-column>
              </a-table>
            </a-card>
          </a-col>
          <a-col :span="9">
            <a-card size="small" title="人工标记" class="detail-section-card">
              <template v-if="getStructuredDetailMark()">
                <a-alert :type="getStructuredDetailMark()?.mark_type === 'exclude' ? 'warning' : 'error'" show-icon style="margin-bottom: 12px">
                  <template #message>
                    <a-space direction="vertical" style="width: 100%">
                      <div>
                        <strong>{{ getStructuredDetailMark()?.mark_type === 'exclude' ? '排除统计' : '异常说明，计入错误' }}</strong>
                        <a-button type="link" size="small" danger @click="clearStructuredDetailMark">清除标记</a-button>
                      </div>
                      <div v-if="getStructuredDetailMark()?.reason">原因：{{ getStructuredDetailMark()?.reason }}</div>
                      <div v-if="getStructuredDetailMark()?.note">备注：{{ getStructuredDetailMark()?.note }}</div>
                    </a-space>
                  </template>
                </a-alert>
              </template>
              <a-empty v-else description="暂无人工标记" style="margin-bottom: 12px" />
              <a-form layout="vertical" size="small">
                <a-form-item label="标记类型">
                  <a-select v-model:value="attributionMarkForm.mark_type">
                    <a-select-option value="exclude">排除统计</a-select-option>
                    <a-select-option value="mismatch_note">异常说明，计入错误</a-select-option>
                  </a-select>
                </a-form-item>
                <a-form-item label="原因">
                  <a-select v-model:value="attributionMarkForm.reason" allow-clear placeholder="选择原因">
                    <a-select-option v-for="reason in attributionReasonOptions" :key="reason" :value="reason">{{ reason }}</a-select-option>
                  </a-select>
                </a-form-item>
                <a-form-item label="备注">
                  <a-textarea v-model:value="attributionMarkForm.note" :rows="3" placeholder="补充说明，可为空" />
                </a-form-item>
                <a-button type="primary" block :loading="attributionMarkSaving" :disabled="!fieldDetailRow.llm?.id" @click="saveStructuredDetailMark">保存标记</a-button>
              </a-form>
            </a-card>
          </a-col>
        </a-row>
      </template>
    </a-modal>

    <a-modal
      v-model:open="attributionMarkOpen"
      width="620px"
      title="字段归因标记"
      ok-text="保存"
      cancel-text="取消"
      :confirm-loading="attributionMarkSaving"
      @ok="saveAttributionMark"
    >
      <template v-if="attributionMarkRow">
        <a-descriptions bordered size="small" :column="2" style="margin-bottom: 12px">
          <a-descriptions-item label="病历号">{{ attributionMarkRow.record_id }}</a-descriptions-item>
          <a-descriptions-item label="字段">{{ attributionMarkRow.field }}</a-descriptions-item>
          <a-descriptions-item label="当前状态">{{ attributionMarkRow.status }}</a-descriptions-item>
          <a-descriptions-item label="LLM结果ID">{{ attributionMarkRow.llm_result_id || '-' }}</a-descriptions-item>
          <a-descriptions-item label="提示词">{{ attributionMarkRow.prompt_template || '-' }}</a-descriptions-item>
          <a-descriptions-item label="ASR方案">{{ attributionMarkRow.asr_slot || '-' }}</a-descriptions-item>
        </a-descriptions>
        <a-alert type="info" show-icon style="margin-bottom: 12px" :message="attributionMarkRow.reason || '当前无系统归因说明'" />
        <a-form layout="vertical">
          <a-form-item label="标记类型">
            <a-select v-model:value="attributionMarkForm.mark_type">
              <a-select-option value="exclude">排除统计</a-select-option>
              <a-select-option value="mismatch_note">异常说明，计入错误</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="原因">
            <a-select v-model:value="attributionMarkForm.reason" allow-clear placeholder="选择原因">
              <a-select-option v-for="reason in attributionReasonOptions" :key="reason" :value="reason">{{ reason }}</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="备注">
            <a-textarea v-model:value="attributionMarkForm.note" :rows="3" placeholder="补充说明，可为空" />
          </a-form-item>
        </a-form>
      </template>
    </a-modal>

    <a-modal
      v-model:open="referenceEditorOpen"
      width="1280px"
      title="编辑标准 ASR 文本"
      ok-text="保存标准文本"
      cancel-text="取消"
      :confirm-loading="referenceEditorSaving"
      @ok="saveReferenceTranscript"
    >
      <template v-if="selectedHistoryRecord">
        <a-alert
          type="info"
          show-icon
          style="margin-bottom: 12px"
          :message="`${selectedHistoryRecord.record_id} · ${selectedHistoryRecord.date}：标准 ASR 只用于优化评估对比，不覆盖任何历史 ASR 结果。`"
        />
        <a-card size="small" class="reference-audio-card">
          <template #title>
            <a-space>
              <span>边听录音边校准</span>
              <a-tag>{{ referenceEditorSegs.length }} 段</a-tag>
            </a-space>
          </template>
          <template #extra>
            <span class="muted">可连续播放；需要精听时可加载完整波形并拖动定位</span>
          </template>
          <AudioPlayer v-if="referenceEditorSegs.length" :segs="referenceEditorSegs" />
          <a-empty v-else description="当前检查记录暂无录音文件" />
        </a-card>
        <a-row :gutter="12">
          <a-col :span="11">
            <a-card size="small" title="底稿 ASR（只读）">
              <a-descriptions size="small" :column="1" style="margin-bottom: 8px">
                <a-descriptions-item label="来源">{{ referenceEditorBase ? historyResultTitle(referenceEditorBase) : (selectedHistoryReference?.base_asr_model_name || '当前标准文本') }}</a-descriptions-item>
                <a-descriptions-item label="字数">{{ referenceEditorBase ? asrTextFromResult(referenceEditorBase).length : 0 }}</a-descriptions-item>
              </a-descriptions>
              <div class="reference-editor-source">{{ referenceEditorBase ? asrTextFromResult(referenceEditorBase) : '未选择底稿；将直接编辑当前标准文本。' }}</div>
            </a-card>
          </a-col>
          <a-col :span="13">
            <a-form layout="vertical">
              <a-form-item label="标准 ASR 文本">
                <div class="reference-annotation-toolbar">
                  <a-space wrap>
                    <span class="muted">选中文本后标注：</span>
                    <a-button size="small" danger @click="applyReferenceAnnotation('red')">标红</a-button>
                    <a-button size="small" @click="applyReferenceAnnotation('orange')">标橙</a-button>
                    <a-button size="small" @click="applyReferenceAnnotation('green')">标绿</a-button>
                    <a-button size="small" @click="clearReferenceAnnotation">清除选中标记</a-button>
                    <span class="muted">已标注 {{ referenceEditorAnnotations.length }} 处</span>
                  </a-space>
                </div>
                <a-textarea
                  v-model:value="referenceEditorText"
                  :rows="18"
                  placeholder="在这里修正为你听到的真实 ASR 标准文本"
                  @select="captureReferenceSelection"
                  @click="captureReferenceSelection"
                  @keyup="captureReferenceSelection"
                />
                <div class="reference-preview-title">标注预览</div>
                <div class="reference-annotation-preview">
                  <span
                    v-for="(segment, index) in referenceEditorSegments"
                    :key="`reference-editor-${index}`"
                    :class="referenceAnnotationClass(segment.type)"
                    :title="segment.note || ''"
                  >{{ segment.text }}</span>
                </div>
              </a-form-item>
              <a-form-item label="备注">
                <a-textarea v-model:value="referenceEditorNote" :rows="3" placeholder="可记录依据，例如：人工听录、某模型底稿修订等" />
              </a-form-item>
            </a-form>
          </a-col>
        </a-row>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { asrOptimizationApi, audioApi, modelApi, patientApi, promptTemplateApi } from '@/api/client'
import type { ModelConfig, PatientExamination } from '@/types'
import AudioPlayer from '@/components/AudioPlayer/index.vue'
import ExamDetailDrawer from '@/components/ExamDetailDrawer/index.vue'

type SlotKey = 'A' | 'B' | 'C'
type MatchStatus = 'match' | 'mismatch' | 'empty'
type AsrSlot = {
  key: SlotKey
  title: string
  model_id?: number
  params: Record<string, any>
  saved_config_hash?: string
}

type AsrPlan = {
  id: string
  backend_id?: number
  name: string
  model_id?: number
  title: string
  params: Record<string, any>
  config_hash?: string
  source: 'history' | 'saved' | 'custom'
}

type AsrResult = {
  id: number
  patient_id: number
  asr_model_id: number
  model_name?: string
  asr_model_name?: string
  full_transcript?: string
  status?: string
  error_message?: string
  source?: string
  experiment_key?: string
  config_hash?: string
  config_snapshot?: any
  segments?: any[]
  asr_integrity?: any
  created_at?: string
}

type AsrReferenceTranscript = {
  id: number
  patient_id: number
  record_id?: string
  date?: string
  base_asr_result_id?: number | null
  base_asr_model_name?: string | null
  base_config_hash?: string | null
  reference_text: string
  reference_annotations?: ReferenceAnnotation[]
  note?: string | null
  is_current?: boolean
  created_at?: string
  updated_at?: string
}

type ReferenceAnnotation = {
  start: number
  end: number
  type: 'red' | 'orange' | 'green'
  note?: string
}

type AsrLogLine = {
  id: number
  time: string
  level: 'info' | 'success' | 'error' | 'warning'
  message: string
}

type OptimizationFieldReviewMark = {
  id: number
  patient_id: number
  field_group: string
  field_key?: string | null
  asr_config_hash?: string | null
  asr_result_id?: number | null
  llm_result_id: number
  llm_model_id?: number | null
  prompt_template_id?: number | null
  prompt_template_name?: string | null
  prompt_content_hash?: string | null
  mark_type: 'exclude' | 'mismatch_note'
  reason?: string | null
  note?: string | null
}

const loading = ref(false)
const asrComparePagination = reactive({
  current: 1,
  pageSize: 10,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
  onChange: (page: number, pageSize: number) => {
    asrComparePagination.current = page
    asrComparePagination.pageSize = pageSize
  },
  onShowSizeChange: (_current: number, pageSize: number) => {
    asrComparePagination.current = 1
    asrComparePagination.pageSize = pageSize
  },
})
const structuredPagination = reactive({
  current: 1,
  pageSize: 20,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
  onChange: (page: number, pageSize: number) => {
    structuredPagination.current = page
    structuredPagination.pageSize = pageSize
  },
  onShowSizeChange: (_current: number, pageSize: number) => {
    structuredPagination.current = 1
    structuredPagination.pageSize = pageSize
  },
})
const attributionPagination = reactive({
  current: 1,
  pageSize: 30,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
  onChange: (page: number, pageSize: number) => {
    attributionPagination.current = page
    attributionPagination.pageSize = pageSize
  },
  onShowSizeChange: (_current: number, pageSize: number) => {
    attributionPagination.current = 1
    attributionPagination.pageSize = pageSize
  },
})
const asrRunning = ref(false)
const llmRunning = ref(false)
const asrProgress = ref('')
const asrLogs = ref<AsrLogLine[]>([])
const asrTotal = ref(0)
const asrCompleted = ref(0)
const asrFailedCount = ref(0)
const llmProgress = ref('')
const fullExporting = ref(false)
const records = ref<PatientExamination[]>([])
const asrModels = ref<ModelConfig[]>([])
const llmModels = ref<ModelConfig[]>([])
const promptTemplates = ref<any[]>([])
const selectedDate = ref('all')
const keyword = ref('')
const activeSlotKey = ref<SlotKey>('A')
const selectedAsrRowKeys = ref<number[]>([])
const selectedHistoryPatientId = ref<number | undefined>(undefined)
const historyModelFilter = ref<number | undefined>(undefined)
const historySourceFilter = ref<string | undefined>(undefined)
const historyIntegrityFilter = ref<string | undefined>(undefined)
const historyAudioModeFilter = ref<string | undefined>(undefined)
const selectedHistoryResultIds = ref<number[]>([])
const asrResultsByRecord = ref<Record<string, Record<string, AsrResult>>>({})
const asrHistoryRows = ref<AsrResult[]>([])
const asrReferencesByRecord = ref<Record<string, AsrReferenceTranscript | null>>({})
const llmResultsByRecord = ref<Record<string, any[]>>({})
const optimizationMarksByKey = ref<Record<string, OptimizationFieldReviewMark>>({})
const savedAsrPlans = ref<AsrPlan[]>([])
const selectedHistoryPlanId = ref<string | undefined>(undefined)
const selectedHistoryAsrModelId = ref<number | undefined>(undefined)
const repairingAsrResultIds = reactive<Record<number, boolean>>({})

const asrSlots = ref<AsrSlot[]>([
  { key: 'A', title: '基线', params: defaultAsrParams() },
  { key: 'B', title: '对比', params: defaultAsrParams() },
  { key: 'C', title: '方案三', params: defaultAsrParams() },
])

const historyModalOpen = ref(false)
const configModalOpen = ref(false)
const editingSlotKey = ref<SlotKey>('A')
const editingPlan = ref<AsrPlan | null>(null)
const slotHotwordsText = ref('')
const slotForm = reactive<AsrSlot>({ key: 'A', title: '', params: defaultAsrParams() })

const selectedTemplateId = ref<number | undefined>(undefined)
const selectedLlmModelId = ref<number | undefined>(undefined)
const selectedLlmRunKey = computed<string | undefined>({
  get() {
    if (!selectedTemplateId.value || !selectedLlmModelId.value) return undefined
    return `${selectedTemplateId.value}:${selectedLlmModelId.value}`
  },
  set(value) {
    if (!value) return
    const [templateId, llmModelId] = String(value).split(':').map((item) => Number(item))
    if (Number.isFinite(templateId)) selectedTemplateId.value = templateId
    if (Number.isFinite(llmModelId)) selectedLlmModelId.value = llmModelId
  },
})
const asrDetailOpen = ref(false)
const asrDetailRow = ref<any>(null)
const examDetailVisible = ref(false)
const examDetailRow = ref<any>(null)
const structuredDetailOpen = ref(false)
const structuredDetailRow = ref<any>(null)
const structuredDetailField = ref<string>('')
const fieldDetailOpen = ref(false)
const fieldDetailRow = ref<any>(null)
const fieldDetailField = ref<string>('')
const attributionFieldFilter = ref<string | undefined>(undefined)
const attributionStatusFilter = ref<string | undefined>(undefined)
const attributionOnlyMarked = ref(false)
const attributionMarkOpen = ref(false)
const attributionMarkSaving = ref(false)
const attributionMarkRow = ref<any>(null)
const attributionMarkForm = reactive({ mark_type: 'exclude' as 'exclude' | 'mismatch_note', reason: '', note: '' })
const chartLlmModelId = ref<number | undefined>(undefined)
const referenceEditorOpen = ref(false)
const referenceEditorSaving = ref(false)
const referenceEditorBase = ref<AsrResult | null>(null)
const referenceEditorText = ref('')
const referenceEditorAnnotations = ref<ReferenceAnnotation[]>([])
const referenceEditorSelection = reactive({ start: 0, end: 0 })
const referenceEditorNote = ref('')

const fieldColumns = [
  { key: 'right_follicle', label: '右卵泡', fields: ['right_follicle_total', 'right_follicles'] },
  { key: 'left_follicle', label: '左卵泡', fields: ['left_follicle_total', 'left_follicles'] },
  { key: 'endometrium_thickness', label: '内膜厚度', fields: ['endometrium_thickness'] },
  { key: 'endometrium_type', label: '内膜类型', fields: ['endometrium_type'] },
  { key: 'right_ovary', label: '右卵巢', fields: ['right_ovary_length', 'right_ovary_width'] },
  { key: 'left_ovary', label: '左卵巢', fields: ['left_ovary_length', 'left_ovary_width'] },
]

const asrCompareColumns = computed(() => [
  { title: '病历号', dataIndex: 'record_id', key: 'record_id', fixed: 'left', width: 105 },
  { title: '日期', dataIndex: 'date', key: 'date', width: 105 },
  { title: `${slotDisplayName(getSlot('A'))} 转写内容`, dataIndex: 'a_text', key: 'a_text', width: 760 },
  { title: `${slotDisplayName(getSlot('B'))} 转写内容`, dataIndex: 'b_text', key: 'b_text', width: 760 },
  { title: `${slotDisplayName(getSlot('C'))} 转写内容`, dataIndex: 'c_text', key: 'c_text', width: 760 },
  { title: '详情', dataIndex: 'action', key: 'action', fixed: 'right', width: 70 },
])

const structuredColumns = [
  { title: '病历号', dataIndex: 'record_id', key: 'record_id', fixed: 'left', width: 105 },
  { title: '日期', dataIndex: 'date', key: 'date', width: 105 },
  { title: '准确率', dataIndex: 'accuracy', key: 'accuracy', width: 90 },
  ...fieldColumns.map((field) => ({ title: field.label, dataIndex: field.key, key: field.key, width: 95 })),
  { title: '详情', dataIndex: 'action', key: 'action', fixed: 'right', width: 70 },
]

const attributionColumns = [
  { title: '病历号', dataIndex: 'record_id', key: 'record_id', fixed: 'left', width: 105 },
  { title: '日期', dataIndex: 'date', key: 'date', width: 105 },
  { title: '字段', dataIndex: 'field', key: 'field', width: 120 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 90 },
  { title: '归因层级', dataIndex: 'attribution_level', key: 'attribution_level', width: 130 },
  { title: '错误类型', dataIndex: 'error_type', key: 'error_type', width: 150 },
  { title: '原因/明细', dataIndex: 'reason', key: 'reason', width: 420 },
  { title: '提示词', dataIndex: 'prompt_template', key: 'prompt_template', width: 160 },
  { title: '操作', dataIndex: 'action', key: 'action', fixed: 'right', width: 100 },
]

const attributionReasonOptions = [
  'ASR/收音问题',
  'ASR数字识别错误',
  'LLM提取错误',
  '提示词规则不足',
  '真实B超数据问题',
  '人工排除',
  '其他',
]

const dateOptions = computed(() => {
  const counts = new Map<string, number>()
  records.value.forEach((item) => counts.set(item.date, (counts.get(item.date) || 0) + 1))
  const dates = Array.from(counts.entries()).sort((a, b) => b[0].localeCompare(a[0])).map(([date, count]) => ({ label: `${date}（${count}）`, value: date }))
  return [{ label: `全部（${records.value.length}）`, value: 'all' }, ...dates]
})

const asrModelOptions = computed(() => asrModels.value.map((model) => ({ label: model.name, value: model.id, disabled: model.status !== 'active' })))
const activeAsrModels = computed(() => asrModels.value.filter((model) => model.status === 'active'))
const selectedSlotModel = computed(() => asrModels.value.find((model) => model.id === slotForm.model_id) || null)
const isMimoSlotModel = computed(() => selectedSlotModel.value?.provider === 'mimo')
const isVolcengineSlotModel = computed(() => selectedSlotModel.value?.provider === 'volcengine')
const configModalTitle = computed(() => editingPlan.value
  ? `编辑历史方案 · ${planDisplayName(editingPlan.value)}`
  : `新增配置 · ASR ${editingSlotKey.value}`)
const llmOptions = computed(() => llmModels.value.map((model) => ({ label: model.name, value: model.id, disabled: model.status !== 'active' })))
const templateOptions = computed(() => promptTemplates.value.map((item) => ({ label: item.name, value: item.id })))
const chartLlmOptions = computed(() => llmModels.value.map((model) => ({ label: model.name, value: model.id })))
const filteredAsrPlanList = computed(() => {
  if (!selectedHistoryAsrModelId.value) return asrPlanList.value
  return asrPlanList.value.filter((plan) => plan.model_id === selectedHistoryAsrModelId.value)
})
const asrPlanOptions = computed(() => filteredAsrPlanList.value.map((plan) => ({
  label: planDisplayName(plan),
  value: plan.id,
})))
const historyAsrModelOptions = computed(() => {
  const ids = new Set(asrPlanList.value.map((plan) => plan.model_id).filter((id): id is number => Number.isFinite(Number(id))))
  return Array.from(ids).map((id) => ({ label: getModelName(id), value: id }))
})
const historySourceOptions = [
  { label: '数据管理', value: 'normal' },
  { label: '优化评估', value: 'asr_optimization' },
  { label: '实验', value: 'experiment' },
]
const historyIntegrityOptions = [
  { label: '完整', value: 'complete' },
  { label: '有空段', value: 'complete_with_empty' },
  { label: '部分缺失/疑似', value: 'partial' },
  { label: '失败', value: 'failed' },
]
const historyAudioModeOptions = [
  { label: '原始分段', value: 'segments' },
  { label: '整段合并', value: 'merged' },
]
const historyPatientOptions = computed(() => filteredRecords.value.map((record) => ({
  label: `${record.record_id} · ${record.date}`,
  value: record.id,
})))
const historyPatientSummaries = computed(() => filteredRecords.value.map((record) => {
  const rows = asrHistoryRows.value.filter((row) => Number(row.patient_id) === Number(record.id))
  let complete = 0
  let empty = 0
  let partial = 0
  let failed = 0
  rows.forEach((row) => {
    const integrity = buildUiAsrIntegrity(record, row)
    const level = String(integrity?.level || row.status || '')
    if (level === 'complete') complete += 1
    else if (level === 'complete_with_empty') empty += 1
    else if (level === 'failed' || row.status === 'failed') failed += 1
    else if (level === 'partial' || level === 'suspect' || row.status === 'partial') partial += 1
  })
  const modelNames = Array.from(new Set(rows.map((row) => row.model_name || row.asr_model_name || getModelName(row.asr_model_id)).filter(Boolean)))
  return {
    id: record.id,
    record_id: record.record_id,
    date: record.date,
    total: rows.length,
    complete,
    empty,
    partial,
    failed,
    hasReference: !!asrReferencesByRecord.value[String(record.id)]?.reference_text,
    modelSummary: modelNames.slice(0, 3).join(' / ') + (modelNames.length > 3 ? ` 等${modelNames.length}个` : ''),
  }
}))
const historyModelFilterOptions = computed(() => {
  const rows = historyAsrResultsForPatient.value
  const ids = Array.from(new Set(rows.map((row) => Number(row.asr_model_id)).filter((id) => Number.isFinite(id))))
  return ids.map((id) => ({ label: getModelName(id), value: id }))
})
const selectedHistoryRecord = computed(() => filteredRecords.value.find((record) => record.id === selectedHistoryPatientId.value) || null)
const historyAsrResultsForPatient = computed(() => {
  if (!selectedHistoryPatientId.value) return []
  return asrHistoryRows.value
    .filter((row) => Number(row.patient_id) === Number(selectedHistoryPatientId.value))
    .sort(compareAsrResultDesc)
})
const filteredHistoryAsrResults = computed(() => historyAsrResultsForPatient.value.filter((row) => {
  if (historyModelFilter.value && Number(row.asr_model_id) !== Number(historyModelFilter.value)) return false
  if (historySourceFilter.value && String(row.source || 'normal') !== historySourceFilter.value) return false
  const integrity = historyResultIntegrity(row)
  const level = String(integrity?.level || row.status || '')
  if (historyIntegrityFilter.value) {
    if (historyIntegrityFilter.value === 'partial') {
      if (!['partial', 'suspect'].includes(level)) return false
    } else if (level !== historyIntegrityFilter.value) {
      return false
    }
  }
  if (historyAudioModeFilter.value) {
    const params = historyResultParams(row)
    const mode = String(params.audio_input_mode || params.recognition_mode || 'segments')
    if (mode !== historyAudioModeFilter.value) return false
  }
  return true
}))
const historyComparePair = computed(() => selectedHistoryResultIds.value
  .map((id) => filteredHistoryAsrResults.value.find((row) => row.id === id))
  .filter((row): row is AsrResult => !!row)
)
const historyCompareSegments = computed(() => {
  if (historyComparePair.value.length !== 2) return { a: [] as TranscriptDiffSegment[], b: [] as TranscriptDiffSegment[] }
  return diffTranscriptSegments(
    normalizeTranscript(asrTextFromResult(historyComparePair.value[0])),
    normalizeTranscript(asrTextFromResult(historyComparePair.value[1])),
  )
})
const historyCompareChanged = computed(() => {
  if (historyComparePair.value.length !== 2) return false
  return normalizeTranscript(asrTextFromResult(historyComparePair.value[0])) !== normalizeTranscript(asrTextFromResult(historyComparePair.value[1]))
})
const selectedHistoryReference = computed(() => {
  if (!selectedHistoryPatientId.value) return null
  return asrReferencesByRecord.value[String(selectedHistoryPatientId.value)] || null
})
const referenceCompareTarget = computed(() => {
  if (!selectedHistoryReference.value || historyComparePair.value.length < 1) return null
  return historyComparePair.value[historyComparePair.value.length - 1]
})
const referenceCompareSegments = computed(() => {
  if (!selectedHistoryReference.value || !referenceCompareTarget.value) return { a: [] as TranscriptDiffSegment[], b: [] as TranscriptDiffSegment[] }
  return diffTranscriptSegments(
    normalizeTranscript(selectedHistoryReference.value.reference_text),
    normalizeTranscript(asrTextFromResult(referenceCompareTarget.value)),
  )
})
const referenceCompareChanged = computed(() => {
  if (!selectedHistoryReference.value || !referenceCompareTarget.value) return false
  return normalizeTranscript(selectedHistoryReference.value.reference_text) !== normalizeTranscript(asrTextFromResult(referenceCompareTarget.value))
})
const referenceEditorSegs = computed(() => {
  const record = selectedHistoryRecord.value as any
  return Array.isArray(record?.segs) ? record.segs : []
})
const referenceEditorSegments = computed(() => buildReferenceAnnotationSegments(referenceEditorText.value, referenceEditorAnnotations.value))

const filteredRecords = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return records.value.filter((record) => {
    const dateMatched = selectedDate.value === 'all' || record.date === selectedDate.value
    const keywordMatched = !kw || String(record.record_id || '').toLowerCase().includes(kw)
    return dateMatched && keywordMatched
  })
})

const activeSlot = computed(() => getSlot(activeSlotKey.value))
const activeSlotLabel = computed(() => {
  const slot = activeSlot.value
  return `${slotDisplayName(slot)} / ${slot.model_id ? getModelName(slot.model_id) : '未选择'} / ${audioModeText(slot.params?.audio_input_mode || 'segments')}`
})
const usedLlmRunOptions = computed(() => {
  const counts = new Map<string, {
    value: string
    label: string
    count: number
    latestAt: number
    recordIds: Set<number>
  }>()
  filteredRecords.value.forEach((record) => {
    const asr = getAsrResult(record, activeSlot.value)
    if (!asr?.id) return
    ;(llmResultsByRecord.value[String(record.id)] || [])
      .filter((row: any) => row.asr_result_id === asr.id && row.prompt_template_id && row.llm_model_id)
      .filter((row: any) => !chartLlmModelId.value || Number(row.llm_model_id) === Number(chartLlmModelId.value))
      .forEach((row: any) => {
        const templateId = Number(row.prompt_template_id)
        const llmModelId = Number(row.llm_model_id)
        const key = `${templateId}:${llmModelId}`
        const latestAt = row.created_at ? new Date(row.created_at).getTime() : 0
        const old = counts.get(key)
        const recordIds = old?.recordIds || new Set<number>()
        recordIds.add(record.id)
        counts.set(key, {
          value: key,
          label: `${row.prompt_template_name || getPromptTemplateName(templateId)} / ${row.full_model_name || row.model_name || row.llm_model_name || getModelName(llmModelId)}`,
          count: recordIds.size,
          latestAt: Math.max(old?.latestAt || 0, latestAt),
          recordIds,
        })
      })
  })
  return Array.from(counts.values())
    .sort((a, b) => b.latestAt - a.latestAt)
    .map(({ recordIds, ...item }) => item)
})
const canRunLlm = computed(() => !!activeSlot.value.model_id && !!selectedTemplateId.value && !!selectedLlmModelId.value && !llmRunning.value)
const canExport = computed(() => asrCompareRows.value.length > 0)
const canExportFull = computed(() => !!activeSlot.value.model_id && !fullExporting.value)
const selectedHistoryPlan = computed(() => asrPlanList.value.find((item) => item.id === selectedHistoryPlanId.value) || null)
const asrProgressPercent = computed(() => asrTotal.value ? Math.round((asrCompleted.value / asrTotal.value) * 100) : 0)
const asrPlanList = computed(() => {
  const plansByHash = new Map<string, AsrPlan>()

  savedAsrPlans.value.forEach((plan) => {
    const hash = getPlanHash(plan)
    if (!hash) return
    plansByHash.set(hash, {
      ...plan,
      id: plan.id || `saved:${hash}`,
      name: planDisplayName(plan),
      title: planDisplayName(plan),
      config_hash: hash,
      source: plan.source || 'custom',
    })
  })

  asrHistoryRows.value.forEach((row) => {
    const snapshot = row.config_snapshot || {}
    const hash = row.config_hash
    if (!hash || !snapshot?.params) return
    const params = { ...(snapshot.params || {}) }
    const historyPlan: AsrPlan = {
      id: `history:${hash}`,
      name: titleFromVariant(snapshot.variant_name || row.model_name || '历史方案'),
      model_id: snapshot.base_asr_model_id || row.asr_model_id,
      title: titleFromVariant(snapshot.variant_name || row.model_name || '历史方案'),
      params,
      config_hash: hash,
      source: 'history',
    }
    const savedPlan = plansByHash.get(hash)
    if (savedPlan) {
      plansByHash.set(hash, {
        ...historyPlan,
        ...savedPlan,
        model_id: savedPlan.model_id || historyPlan.model_id,
        params: Object.keys(savedPlan.params || {}).length ? savedPlan.params : historyPlan.params,
        config_hash: hash,
      })
    } else {
      plansByHash.set(hash, historyPlan)
    }
  })

  return Array.from(plansByHash.values())
})
const selectedAsrRecordIdSet = computed(() => new Set(selectedAsrRowKeys.value.map((key) => Number(key))))
const asrExecutionRecords = computed(() => {
  if (!selectedAsrRowKeys.value.length) return filteredRecords.value
  return filteredRecords.value.filter((record) => selectedAsrRecordIdSet.value.has(record.id))
})
const asrRowSelection = computed(() => ({
  selectedRowKeys: selectedAsrRowKeys.value,
  preserveSelectedRowKeys: false,
  getCheckboxProps: () => ({ disabled: asrRunning.value }),
  onChange: (keys: (string | number)[]) => {
    selectedAsrRowKeys.value = keys.map((key) => Number(key)).filter((key) => Number.isFinite(key))
  },
}))

const asrCompareRows = computed(() => filteredRecords.value.map((record) => {
  const aSlot = getSlot('A')
  const bSlot = getSlot('B')
  const cSlot = getSlot('C')
  const a = getAsrResult(record, aSlot)
  const b = getAsrResult(record, bSlot)
  const c = getAsrResult(record, cSlot)
  const aText = normalizeTranscript(asrTextFromResult(a))
  const bText = normalizeTranscript(asrTextFromResult(b))
  const cText = normalizeTranscript(asrTextFromResult(c))
  const diffSegments = diffTranscriptSegments(aText, bText)
  const diffSegmentsAC = diffTranscriptSegments(aText, cText)
  const aIntegrity = buildUiAsrIntegrity(record, a)
  const bIntegrity = buildUiAsrIntegrity(record, b)
  const cIntegrity = buildUiAsrIntegrity(record, c)
  const configuredHashes = [aSlot, bSlot, cSlot]
    .filter((slot) => !!slot.model_id)
    .map((slot) => slotConfigHash(slot))
  const sameConfig = configuredHashes.length >= 2 && new Set(configuredHashes).size === 1
  return {
    patient_id: record.id,
    record_id: record.record_id,
    date: record.date,
    a_result_id: a?.id,
    b_result_id: b?.id,
    c_result_id: c?.id,
    a_result: a,
    b_result: b,
    c_result: c,
    a_status: aIntegrity.level === 'complete_with_empty' ? 'complete_with_empty' : (a?.status || 'missing'),
    b_status: bIntegrity.level === 'complete_with_empty' ? 'complete_with_empty' : (b?.status || 'missing'),
    c_status: cIntegrity.level === 'complete_with_empty' ? 'complete_with_empty' : (c?.status || 'missing'),
    a_integrity: aIntegrity,
    b_integrity: bIntegrity,
    c_integrity: cIntegrity,
    same_config: sameConfig,
    a_text: aText,
    b_text: bText,
    c_text: cText,
    a_segments: diffSegments.a,
    b_segments: diffSegments.b,
    c_segments: diffSegmentsAC.b,
    a_error: a?.error_message || '',
    b_error: b?.error_message || '',
    c_error: c?.error_message || '',
  }
}))

const structuredRows = computed(() => filteredRecords.value.map((record) => {
  const asr = getAsrResult(record, activeSlot.value)
  const llm = pickLlmForAsr(record, asr?.id)
  const fieldStatus: Record<string, MatchStatus> = {}
  const fieldNotes: Record<string, string> = {}
  fieldColumns.forEach((field) => {
    fieldStatus[field.key] = getGroupMatchStatus(record, llm, field)
    fieldNotes[field.key] = getGroupIssueText(record, llm, field)
  })
  const row = {
    patient_id: record.id,
    record_id: record.record_id,
    date: record.date,
    has_audio: !!record.has_audio || !!record.segs?.length,
    seg_count: record.segs?.length || 0,
    has_result: !!record.result,
    asr_slot: slotDisplayName(activeSlot.value),
    llm_name: llm?.prompt_template_name || llm?.model_name || llm?.llm_model_name || '-',
    field_status: fieldStatus,
    field_notes: fieldNotes,
    llm,
    record,
  }
  return {
    ...row,
    accuracy: calculateStructuredRowAccuracy(row),
    raw_accuracy: llm?.accuracy_without_remark ?? llm?.accuracy ?? null,
  }
}))

const structuredFieldStats = computed(() => fieldColumns.map((field) => {
  const rows = structuredRows.value
  const comparableRows = rows.filter((row) => row.has_result && row.llm)
  const denominator = comparableRows.filter((row) => getAttributionStatus(row.field_status[field.key], getRowFieldMark(row, field.key)) !== '排除').length
  const matched = comparableRows.filter((row) => getStatAttributionStatus(row, field.key) === '正确').length
  return { key: field.key, label: field.label, total: denominator, matched, rate: denominator ? matched / denominator : 1 }
}))

const follicleDetailStats = computed(() => {
  const detailFields = [
    { key: 'right_follicles', group: 'right_follicle', label: '右卵泡明细' },
    { key: 'left_follicles', group: 'left_follicle', label: '左卵泡明细' },
  ]
  const rows = structuredRows.value.filter((row) => row.has_result && row.llm)
  const stats = detailFields.map((field) => {
    const validRows = rows.filter((row) => getAttributionStatus(row.field_status[field.group], getRowFieldMark(row, field.group)) !== '排除')
    const scores = validRows.map((row) => follicleDetailScore(row, field.key))
    const matchedScore = scores.reduce((sum, item) => sum + item.rate, 0)
    return {
      key: field.key,
      label: field.label,
      total: validRows.length,
      matched: Number(matchedScore.toFixed(2)),
      rate: validRows.length ? matchedScore / validRows.length : 1,
    }
  })
  const total = stats.reduce((sum, item) => sum + item.total, 0)
  const matched = stats.reduce((sum, item) => sum + item.matched, 0)
  return [
    {
      key: 'follicle_detail_average',
      label: '左右卵泡明细平均',
      total,
      matched,
      rate: total ? matched / total : 1,
    },
    ...stats,
  ]
})

const chartHeatmapFields = computed(() => [
  ...fieldColumns.map((field) => ({ key: field.key, label: field.label, type: 'field' as const, group: field.key })),
  { key: 'right_follicles_detail', label: '右卵泡明细', type: 'follicle' as const, group: 'right_follicle', subKey: 'right_follicles' },
  { key: 'left_follicles_detail', label: '左卵泡明细', type: 'follicle' as const, group: 'left_follicle', subKey: 'left_follicles' },
])

const analysisLlmRows = computed(() => {
  const latestByIdentity = new Map<string, { record: PatientExamination; llm: any; createdAt: number; id: number }>()
  filteredRecords.value.forEach((record) => {
    const asr = getAsrResult(record, activeSlot.value)
    if (!asr?.id) return
    ;(llmResultsByRecord.value[String(record.id)] || []).forEach((llm: any) => {
      if (!llm?.id || !record.result) return
      if (llm.status && llm.status !== 'success') return
      if (!llm.asr_result_id || !llm.prompt_template_id || !llm.llm_model_id) return
      if (Number(llm.asr_result_id) !== Number(asr.id)) return
      if (chartLlmModelId.value && Number(llm.llm_model_id) !== Number(chartLlmModelId.value)) return
      const identity = [
        record.id,
        llm.asr_result_id,
        Number(llm.prompt_template_id),
        Number(llm.llm_model_id),
      ].join(':')
      const createdAt = llm.created_at ? new Date(llm.created_at).getTime() : 0
      const id = Number(llm.id || 0)
      const old = latestByIdentity.get(identity)
      if (!old || createdAt > old.createdAt || (createdAt === old.createdAt && id > old.id)) {
        latestByIdentity.set(identity, { record, llm, createdAt, id })
      }
    })
  })
  return Array.from(latestByIdentity.values()).map(({ record, llm }) => buildAnalysisStructuredRow(record, llm))
})

const analysisChartGroups = computed(() => {
  const groups = new Map<string, { key: string; label: string; shortLabel: string; rows: any[] }>()
  analysisLlmRows.value.forEach((row) => {
    const group = chartGroupInfo(row)
    const old = groups.get(group.key)
    if (old) {
      old.rows.push(row)
    } else {
      groups.set(group.key, { ...group, rows: [row] })
    }
  })

  return Array.from(groups.values())
    .map((group) => {
      const fieldRates = Object.fromEntries(chartHeatmapFields.value.map((field) => [field.key, aggregateChartFieldRate(group.rows, field)]))
      const fieldStats = fieldColumns.map((field) => fieldRates[field.key]).filter(Boolean)
      const fieldDenominator = fieldStats.reduce((sum, item: any) => sum + Number(item.total || 0), 0)
      const fieldMatched = fieldStats.reduce((sum, item: any) => sum + Number(item.matched || 0), 0)
      const follicleStats = ['right_follicles_detail', 'left_follicles_detail']
        .map((key) => fieldRates[key])
        .filter((item: any) => item && item.total)
      const follicleRate = follicleStats.length
        ? follicleStats.reduce((sum: number, item: any) => sum + Number(item.rate || 0), 0) / follicleStats.length
        : 1
      return {
        ...group,
        sampleCount: new Set(group.rows.map((row) => row.patient_id)).size,
        overallRate: fieldDenominator ? fieldMatched / fieldDenominator : 1,
        follicleRate,
        fieldRates,
      }
    })
    .sort((a, b) => b.overallRate - a.overallRate || b.sampleCount - a.sampleCount || a.label.localeCompare(b.label))
})

const heatmapGridColumns = computed(() => `120px repeat(${Math.max(analysisChartGroups.value.length, 1)}, minmax(126px, 1fr))`)

const attributionRows = computed(() => {
  const rows: any[] = []
  structuredRows.value.forEach((row) => {
    fieldColumns.forEach((field) => {
      rows.push(buildAttributionRow(row, field))
    })
  })
  return rows
})

const filteredAttributionRows = computed(() => attributionRows.value.filter((row) => {
  if (attributionFieldFilter.value && row.group !== attributionFieldFilter.value) return false
  if (attributionStatusFilter.value && row.status !== attributionStatusFilter.value) return false
  if (attributionOnlyMarked.value && !row.has_mark) return false
  return true
}))

const attributionOverallStats = computed(() => {
  const rows = filteredAttributionRows.value
  const total = rows.length
  const correct = rows.filter((row) => row.stat_status === '正确').length
  const error = rows.filter((row) => row.status === '错误').length
  const excluded = rows.filter((row) => row.status === '排除').length
  const abnormal = rows.filter((row) => row.status === '异常').length
  const missing = rows.filter((row) => row.status === '未提取').length
  const denominator = total - excluded
  const accuracy = denominator ? correct / denominator : 0
  return { total, correct, error, excluded, abnormal, missing, denominator, accuracy }
})

const examDetailData = computed(() => {
  const row = examDetailRow.value
  if (!row) return null
  const asr = getActiveAsrResult(row)
  const llm = row.llm || {}
  return {
    record_id: row.record_id,
    date: row.date,
    segs_count: row.record?.segs?.length || 0,
    segs: row.record?.segs || [],
    has_ground_truth: !!row.record?.result,
    asr: {
      model_name: asr?.model_name || asr?.asr_model_name || row.asr_slot || '',
      full_transcript: asr?.full_transcript || '',
      status: asr?.status || (asr ? 'success' : 'pending'),
      asr_source: asr?.source === 'asr_optimization' ? 'generated' : 'reused',
    },
    llm: {
      model_name: llm.model_name || llm.llm_model_name || '',
      summary_text: llm.summary_text || llm.summary || '',
      structured_result: llm.structured_result || llm.structured || {},
      raw_output: llm.raw_output || llm.raw_text || '',
      prompt_template_name: llm.prompt_template_name || '',
      accuracy: row.accuracy,
      status: llm.status || (llm.id ? 'success' : 'pending'),
      error_message: llm.error_message || '',
      missing_fields: llm.missing_fields || [],
    },
    ground_truth: row.record?.result || {},
    experiment: {
      batch_name: `优化评估 · ${row.asr_slot || activeSlotLabel.value}`,
      task_status: llm.status || (llm.id ? 'success' : 'pending'),
    },
  }
})

watch(selectedDate, () => {
  loadAsrResults()
  loadLlmResults()
  loadAsrReferences()
})

watch(chartLlmModelId, (modelId) => {
  if (modelId) selectedLlmModelId.value = modelId
})

watch(filteredRecords, (rows) => {
  if (!selectedAsrRowKeys.value.length) return
  const visibleIds = new Set(rows.map((record) => record.id))
  selectedAsrRowKeys.value = selectedAsrRowKeys.value.filter((id) => visibleIds.has(id))
})

watch(filteredRecords, (rows) => {
  if (selectedHistoryPatientId.value && rows.some((record) => record.id === selectedHistoryPatientId.value)) return
  selectedHistoryPatientId.value = rows[0]?.id
  selectedHistoryResultIds.value = []
}, { immediate: true })

watch([selectedHistoryPatientId, historyModelFilter, historySourceFilter, historyIntegrityFilter, historyAudioModeFilter], () => {
  const visibleIds = new Set(filteredHistoryAsrResults.value.map((row) => row.id))
  selectedHistoryResultIds.value = selectedHistoryResultIds.value.filter((id) => visibleIds.has(id))
})

watch(selectedHistoryAsrModelId, () => {
  if (!selectedHistoryPlanId.value) return
  const selected = asrPlanList.value.find((plan) => plan.id === selectedHistoryPlanId.value)
  if (selectedHistoryAsrModelId.value && selected?.model_id !== selectedHistoryAsrModelId.value) {
    selectedHistoryPlanId.value = undefined
  }
})

onMounted(loadAll)

async function loadAll() {
  loading.value = true
  try {
    const [recordData, asrData, llmData, templateData, planData] = await Promise.all([
      audioApi.getRecords(),
      modelApi.list('asr'),
      modelApi.list('llm'),
      promptTemplateApi.list(),
      asrOptimizationApi.listPlans(),
    ])
    records.value = recordData as PatientExamination[]
    asrModels.value = asrData as ModelConfig[]
    llmModels.value = llmData as ModelConfig[]
    promptTemplates.value = templateData as any[]
    savedAsrPlans.value = normalizeBackendPlans(planData as any[])
    await migrateLocalPlansToBackend()
    savedAsrPlans.value = normalizeBackendPlans(await asrOptimizationApi.listPlans() as any[])
    if (!selectedLlmModelId.value) selectedLlmModelId.value = llmModels.value.find((m) => m.is_default)?.id || llmModels.value[0]?.id
    if (!selectedTemplateId.value) selectedTemplateId.value = promptTemplates.value.find((t: any) => t.is_default)?.id || promptTemplates.value[0]?.id
    await Promise.all([loadAsrResults(), loadLlmResults(), loadAsrReferences()])
  } finally {
    loading.value = false
  }
}

async function loadAsrResults() {
  const ids = filteredRecords.value.map((record) => record.id)
  const allIds = records.value.map((record) => record.id)
  if (!ids.length) {
    asrResultsByRecord.value = {}
    asrHistoryRows.value = []
    return
  }
  const [data, historyData] = await Promise.all([
    patientApi.listAsrResultsBatch(ids) as Promise<Record<string, AsrResult[]>>,
    allIds.length === ids.length
      ? Promise.resolve(null)
      : patientApi.listAsrResultsBatch(allIds) as Promise<Record<string, AsrResult[]>>,
  ])
  const next: Record<string, Record<string, AsrResult>> = {}
  ids.forEach((id) => { next[String(id)] = {} })
  Object.entries(data || {}).forEach(([recordId, rows]) => {
    next[recordId] = next[recordId] || {}
    ;(rows || []).forEach((row) => {
      const key = resultSlotKey(row)
      const old = next[recordId][key]
      if (!old || compareAsrResultDesc(row, old) < 0) next[recordId][key] = row
    })
  })
  const flatRows: AsrResult[] = []
  Object.values(historyData || data || {}).forEach((rows) => {
    ;(rows || []).forEach((row) => flatRows.push(row))
  })
  asrResultsByRecord.value = next
  asrHistoryRows.value = flatRows
}

async function loadAsrReferences() {
  const ids = filteredRecords.value.map((record) => record.id)
  if (!ids.length) {
    asrReferencesByRecord.value = {}
    return
  }
  const data = await patientApi.listAsrReferencesBatch(ids) as Record<string, AsrReferenceTranscript>
  const next: Record<string, AsrReferenceTranscript | null> = {}
  ids.forEach((id) => {
    next[String(id)] = data?.[String(id)] || null
  })
  asrReferencesByRecord.value = next
}

async function loadLlmResults() {
  const next: Record<string, any[]> = {}
  await Promise.all(filteredRecords.value.map(async (record) => {
    try {
      next[String(record.id)] = await patientApi.listLlmResults(record.id, { include_optimization: true }) as any[]
    } catch {
      next[String(record.id)] = []
    }
  }))
  llmResultsByRecord.value = next
  await loadOptimizationFieldMarks()
}

async function loadOptimizationFieldMarks() {
  const ids = Object.values(llmResultsByRecord.value)
    .flat()
    .map((row: any) => Number(row.id))
    .filter((id) => Number.isFinite(id))
  if (!ids.length) {
    optimizationMarksByKey.value = {}
    return
  }
  const marks = await asrOptimizationApi.listFieldReviewMarks(ids) as OptimizationFieldReviewMark[]
  const next: Record<string, OptimizationFieldReviewMark> = {}
  ;(marks || []).forEach((mark) => {
    next[optimizationMarkKey(mark.llm_result_id, mark.field_group, mark.field_key || undefined)] = mark
  })
  optimizationMarksByKey.value = next
}

function getSlot(key: SlotKey) {
  return asrSlots.value.find((slot) => slot.key === key) || asrSlots.value[0]
}

function slotVariantName(slot: AsrSlot) {
  const modelName = slot.model_id ? getModelName(slot.model_id) : 'ASR'
  return `ASR ${slot.key}-${slot.title || modelName}`
}

function slotDisplayName(slot: AsrSlot) {
  const title = String(slot.title || '').trim()
  return title ? `ASR ${slot.key}-${title}` : `ASR ${slot.key}-未命名`
}

function slotTagColor(key: SlotKey) {
  if (key === 'A') return 'blue'
  if (key === 'B') return 'purple'
  return 'cyan'
}

function resultSlotKey(result: AsrResult) {
  // 优化评估结果的业务身份是「检查记录 + 配置指纹」。
  // experiment_key 只是发起时的筛选上下文（all / 某日期），不能用于结果复用判断；
  // 否则同一条检查记录在 20260624 下跑完 ASR，切回 all 或其它视图时会被误判为无结果。
  if (result.source === 'asr_optimization' && result.config_hash) {
    return result.config_hash || ''
  }
  return `model:${result.asr_model_id}`
}

function getAsrResult(record: PatientExamination, slot: AsrSlot) {
  if (!slot.model_id) return null
  return asrResultsByRecord.value[String(record.id)]?.[slotConfigHash(slot)] || null
}

function historyResultParams(result: AsrResult) {
  const snapshot = result.config_snapshot || {}
  return snapshot?.params || {}
}

function historyResultIntegrity(result: AsrResult) {
  if (selectedHistoryRecord.value) return buildUiAsrIntegrity(selectedHistoryRecord.value, result)
  return result.asr_integrity || {}
}

function historyResultStatus(result: AsrResult) {
  const level = String(historyResultIntegrity(result)?.level || '')
  if (level === 'complete_with_empty') return 'complete_with_empty'
  if (level === 'complete') return 'success'
  return result.status || 'missing'
}

function historyResultTitle(result: AsrResult) {
  const snapshot = result.config_snapshot || {}
  const variant = snapshot?.variant_name || ''
  const model = result.model_name || result.asr_model_name || getModelName(result.asr_model_id)
  const title = titleFromVariant(variant || model)
  return `${title} · #${result.id}`
}

function sourceText(source?: string) {
  if (source === 'asr_optimization') return '优化评估'
  if (source === 'experiment') return '实验'
  return '数据管理'
}

function shortDateTime(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function toggleHistoryResultSelection(id: number) {
  const exists = selectedHistoryResultIds.value.includes(id)
  if (exists) {
    selectedHistoryResultIds.value = selectedHistoryResultIds.value.filter((item) => item !== id)
    return
  }
  selectedHistoryResultIds.value = [...selectedHistoryResultIds.value, id].slice(-2)
}

function selectHistoryPatient(id: number) {
  if (selectedHistoryPatientId.value === id) return
  selectedHistoryPatientId.value = id
  selectedHistoryResultIds.value = []
  historyModelFilter.value = undefined
  historySourceFilter.value = undefined
  historyIntegrityFilter.value = undefined
  historyAudioModeFilter.value = undefined
}

function openReferenceEditor(base?: AsrResult) {
  if (!selectedHistoryPatientId.value) {
    message.warning('请先选择检查记录')
    return
  }
  const current = selectedHistoryReference.value
  referenceEditorBase.value = base || null
  referenceEditorText.value = base ? asrTextFromResult(base) : (current?.reference_text || '')
  referenceEditorAnnotations.value = base ? [] : normalizeReferenceAnnotations(current?.reference_annotations || [], current?.reference_text || '')
  referenceEditorSelection.start = 0
  referenceEditorSelection.end = 0
  referenceEditorNote.value = current?.note || ''
  referenceEditorOpen.value = true
}

async function saveReferenceTranscript() {
  if (!selectedHistoryPatientId.value) {
    message.warning('请先选择检查记录')
    return
  }
  const text = referenceEditorText.value.trim()
  if (!text) {
    message.warning('标准 ASR 文本不能为空')
    return
  }
  referenceEditorSaving.value = true
  try {
    const saved = await patientApi.saveAsrReference(selectedHistoryPatientId.value, {
      base_asr_result_id: referenceEditorBase.value?.id,
      reference_text: text,
      reference_annotations: normalizeReferenceAnnotations(referenceEditorAnnotations.value, text),
      note: referenceEditorNote.value.trim(),
    }) as AsrReferenceTranscript
    asrReferencesByRecord.value = {
      ...asrReferencesByRecord.value,
      [String(selectedHistoryPatientId.value)]: saved,
    }
    referenceEditorOpen.value = false
    message.success('标准 ASR 文本已保存')
  } finally {
    referenceEditorSaving.value = false
  }
}

function captureReferenceSelection(event: Event) {
  const target = event.target as HTMLTextAreaElement | HTMLInputElement | null
  if (!target || typeof target.selectionStart !== 'number' || typeof target.selectionEnd !== 'number') return
  referenceEditorSelection.start = target.selectionStart
  referenceEditorSelection.end = target.selectionEnd
}

function applyReferenceAnnotation(type: ReferenceAnnotation['type']) {
  const start = Math.min(referenceEditorSelection.start, referenceEditorSelection.end)
  const end = Math.max(referenceEditorSelection.start, referenceEditorSelection.end)
  if (end <= start) {
    message.warning('请先在标准 ASR 文本框中选中一段文字')
    return
  }
  const next = referenceEditorAnnotations.value
    .filter((item) => item.end <= start || item.start >= end)
    .concat({ start, end, type })
  referenceEditorAnnotations.value = normalizeReferenceAnnotations(next, referenceEditorText.value)
}

function clearReferenceAnnotation() {
  const start = Math.min(referenceEditorSelection.start, referenceEditorSelection.end)
  const end = Math.max(referenceEditorSelection.start, referenceEditorSelection.end)
  if (end <= start) {
    message.warning('请先选中要清除标记的文字')
    return
  }
  referenceEditorAnnotations.value = referenceEditorAnnotations.value.filter((item) => item.end <= start || item.start >= end)
}

function normalizeReferenceAnnotations(value: any[], text: string): ReferenceAnnotation[] {
  const textLength = String(text || '').length
  if (!Array.isArray(value)) return []
  return value
    .map((item: any) => {
      const start = Math.max(0, Math.min(Number(item?.start || 0), textLength))
      const end = Math.max(0, Math.min(Number(item?.end || 0), textLength))
      const type = ['red', 'orange', 'green'].includes(item?.type) ? item.type : 'red'
      return { start, end, type, note: item?.note || '' } as ReferenceAnnotation
    })
    .filter((item) => Number.isFinite(item.start) && Number.isFinite(item.end) && item.end > item.start)
    .sort((a, b) => a.start - b.start || a.end - b.end)
}

function buildReferenceAnnotationSegments(text: string, annotations?: ReferenceAnnotation[]) {
  const source = String(text || '')
  const marks = normalizeReferenceAnnotations(annotations || [], source)
  const segments: { text: string; type?: ReferenceAnnotation['type']; note?: string }[] = []
  let cursor = 0
  marks.forEach((mark) => {
    if (mark.start > cursor) segments.push({ text: source.slice(cursor, mark.start) })
    segments.push({ text: source.slice(mark.start, mark.end), type: mark.type, note: mark.note })
    cursor = mark.end
  })
  if (cursor < source.length) segments.push({ text: source.slice(cursor) })
  return segments.length ? segments : [{ text: source }]
}

function referenceDisplaySegments(reference?: AsrReferenceTranscript | null) {
  if (!reference) return []
  return buildReferenceAnnotationSegments(reference.reference_text || '', reference.reference_annotations || [])
}

function referenceAnnotationClass(type?: ReferenceAnnotation['type']) {
  if (type === 'red') return 'reference-mark reference-mark-red'
  if (type === 'orange') return 'reference-mark reference-mark-orange'
  if (type === 'green') return 'reference-mark reference-mark-green'
  return ''
}

function isUsableAsrResult(result?: AsrResult | null) {
  const level = String(result?.asr_integrity?.level || '')
  return result?.status === 'success' || level === 'complete' || level === 'complete_with_empty'
}

function asrTextFromResult(result?: AsrResult | null) {
  if (!result) return ''
  if (result.full_transcript) return result.full_transcript
  if (Array.isArray(result.segments)) {
    return result.segments.map((item: any) => item?.text || '').filter(Boolean).join('\n')
  }
  return ''
}

function extractNumbers(text: string) {
  return String(text || '').match(/\d+(?:\.\d+)?/g) || []
}

function getRecordAudioSegmentCount(record: PatientExamination) {
  return Number((record as any).seg_count || (record as any).segs_count || (record as any).segs?.length || 0)
}

function buildUiAsrIntegrity(record: PatientExamination, result?: AsrResult | null) {
  if (!result) {
    return { level: 'missing', label: '未转写', score: 0, reasons: ['暂无 ASR 结果'], missing_segment_indices: [] }
  }
  const base = result.asr_integrity || {}
  const text = asrTextFromResult(result)
  const total = Number(base.audio_segment_count || getRecordAudioSegmentCount(record) || 0)
  const segments = Array.isArray(result.segments) ? result.segments : []
  const resultSegmentCount = Number(base.result_segment_count ?? segments.length ?? 0)
  const existing = new Set(
    segments
      .map((item: any) => Number(item?.seg_index))
      .filter((idx: number) => Number.isFinite(idx) && idx > 0 && String(segments.find((s: any) => Number(s?.seg_index) === idx)?.text || '').trim()),
  )
  const missing = Array.isArray(base.missing_segment_indices)
    ? base.missing_segment_indices
    : total ? Array.from({ length: total }, (_, idx) => idx + 1).filter((idx) => !existing.has(idx)) : []
  const allResults = Object.values(asrResultsByRecord.value[String(record.id)] || {})
  const maxTextLen = Math.max(0, ...allResults.map((item) => asrTextFromResult(item).length))
  const maxNumberCount = Math.max(0, ...allResults.map((item) => extractNumbers(asrTextFromResult(item)).length))
  const textLen = text.length
  const numberCount = extractNumbers(text).length
  const reasons = [...(base.reasons || [])]
  let level = base.level || 'complete'
  let label = base.label || '完整'
  let score = Number(base.score ?? 100)

  if (result.status === 'failed' || result.status === 'partial') {
    level = textLen ? 'partial' : 'failed'
    label = textLen && total ? `部分转写 ${resultSegmentCount}/${total}` : textLen ? '部分转写' : total ? `失败 0/${total}` : '失败'
  } else if (missing.length && total && resultSegmentCount > 1) {
    level = 'partial'
    label = `部分转写 ${resultSegmentCount}/${total}`
    reasons.push(`缺失分段：${missing.join('、')}`)
  }
  if (result.status === 'success' && maxTextLen > 0 && textLen > 0 && textLen < maxTextLen * 0.7) {
    if (level === 'complete') {
      level = 'suspect'
      label = '疑似不完整'
    }
    score = Math.min(score, 70)
    reasons.push(`文本长度明显偏低：${textLen}/${maxTextLen}`)
  }
  if (result.status === 'success' && maxNumberCount > 0 && numberCount < maxNumberCount * 0.7) {
    if (level === 'complete') {
      level = 'suspect'
      label = '疑似漏数字'
    }
    score = Math.min(score, 70)
    reasons.push(`数字数量明显偏低：${numberCount}/${maxNumberCount}`)
  }
  return {
    ...base,
    level,
    label,
    score,
    text_length: textLen,
    number_count: numberCount,
    audio_segment_count: total || base.audio_segment_count,
    result_segment_count: resultSegmentCount,
    missing_segment_indices: missing,
    reasons: Array.from(new Set(reasons.filter(Boolean))),
  }
}

function asrIntegrityColor(integrity?: any) {
  const level = String(integrity?.level || '')
  if (level === 'complete') return 'green'
  if (level === 'complete_with_empty') return 'blue'
  if (level === 'partial' || level === 'suspect') return 'orange'
  if (level === 'failed') return 'red'
  if (level === 'running') return 'processing'
  return 'default'
}

function asrIntegrityText(integrity?: any) {
  return integrity?.label || '未转写'
}

function asrIntegrityNote(integrity?: any) {
  if (!integrity) return ''
  const reasons = Array.isArray(integrity.reasons) ? integrity.reasons : []
  const missing = Array.isArray(integrity.missing_segment_indices) ? integrity.missing_segment_indices : []
  const parts: string[] = []
  if (missing.length) parts.push(`缺失：${missing.join('、')}段`)
  if (Number.isFinite(Number(integrity.text_length))) parts.push(`字数：${Number(integrity.text_length)}`)
  if (Number.isFinite(Number(integrity.number_count))) parts.push(`数字：${Number(integrity.number_count)}`)
  if (reasons.length) parts.push(...reasons.slice(0, 2))
  return Array.from(new Set(parts.filter(Boolean))).join('；')
}

function canRepairAsrResult(row: any, key: SlotKey) {
  const result = compareRowValue(row, key, 'result')
  const integrity = compareRowValue(row, key, 'integrity')
  const missing = Array.isArray(integrity?.missing_segment_indices) ? integrity.missing_segment_indices : []
  return !!result?.id && missing.length > 0 && ['partial', 'failed', 'suspect'].includes(String(integrity?.level || result.status || ''))
}

async function repairMissingSegments(row: any, key: SlotKey) {
  const result = compareRowValue(row, key, 'result')
  if (!result?.id || !row?.patient_id) return
  repairingAsrResultIds[result.id] = true
  try {
    appendAsrLog('info', `${row.record_id} / ASR ${key} 开始补跑缺失段：#${result.id}`)
    const repaired: any = await patientApi.repairAsrMissingSegments(row.patient_id, result.id)
    const failed = Array.isArray(repaired?.failed_segments) ? repaired.failed_segments.length : 0
    if (failed) {
      appendAsrLog('warning', `${row.record_id} / ASR ${key} 补跑完成但仍有 ${failed} 段失败：${repaired?.asr_integrity?.label || repaired?.status || ''}`)
      message.warning(`${row.record_id} / ASR ${key} 补跑完成，但仍有缺失段`)
    } else {
      appendAsrLog('success', `${row.record_id} / ASR ${key} 补跑完成：${repaired?.asr_integrity?.label || repaired?.status || '已更新'}`)
      message.success(`${row.record_id} / ASR ${key} 补跑完成`)
    }
    await loadAsrResults()
  } catch (error: any) {
    const msg = error?.response?.data?.detail || error?.message || '补跑失败'
    appendAsrLog('error', `${row.record_id} / ASR ${key} 补跑失败：${msg}`)
    message.error(`${row.record_id} / ASR ${key} 补跑失败：${msg}`)
  } finally {
    repairingAsrResultIds[result.id] = false
  }
}

function compareRowValue(row: any, key: SlotKey, field: 'result' | 'integrity' | 'status' | 'text' | 'error') {
  const prefix = key.toLowerCase()
  return row?.[`${prefix}_${field}`]
}

function slotStats(slot: AsrSlot) {
  let success = 0
  let failed = 0
  let missing = 0
  filteredRecords.value.forEach((record) => {
    const result = getAsrResult(record, slot)
    if (isUsableAsrResult(result)) success += 1
    else if (result?.status === 'failed') failed += 1
    else missing += 1
  })
  return { success, failed, missing }
}

function clearAsrSelection() {
  selectedAsrRowKeys.value = []
}

function experimentKey() {
  return `asr_optimize:${selectedDate.value || 'all'}`
}

function slotConfigSnapshot(slot: AsrSlot) {
  return {
    base_asr_model_id: slot.model_id,
    params: normalizeForHash(effectiveAsrParamsForHash(slot.params || {})),
  }
}

function effectiveAsrParamsForHash(params: Record<string, any>) {
  const next = { ...(params || {}) }
  // 与后端 _apply_asr_feature_switches 保持一致：
  // 已填写但未启用的热词/词表不参与实际调用，也不应改变优化评估结果指纹。
  if (next.use_boosting_table === false) {
    delete next.boosting_table_id
    delete next.boosting_table_name
  }
  if (next.use_correct_table === false) {
    delete next.correct_table_id
    delete next.correct_table_name
  }
  if (next.use_context_hotwords === false) {
    delete next.hotwords
    delete next.context_text
    delete next.context_mode
  }
  return next
}

function slotConfigHash(slot: AsrSlot) {
  if (slot.saved_config_hash) return slot.saved_config_hash
  return simpleHash(stableStringify(slotConfigSnapshot(slot)))
}

function normalizeForHash(value: any): any {
  if (Array.isArray(value)) return value.map(normalizeForHash).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().filter((key) => value[key] !== undefined && value[key] !== null && value[key] !== '').map((key) => [key, normalizeForHash(value[key])]))
  }
  return value
}

function stableStringify(value: any) {
  return JSON.stringify(normalizeForHash(value))
}

function simpleHash(text: string) {
  let h1 = 0xdeadbeef
  let h2 = 0x41c6ce57
  for (let i = 0; i < text.length; i += 1) {
    const ch = text.charCodeAt(i)
    h1 = Math.imul(h1 ^ ch, 2654435761)
    h2 = Math.imul(h2 ^ ch, 1597334677)
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909)
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909)
  return `${(h2 >>> 0).toString(16).padStart(8, '0')}${(h1 >>> 0).toString(16).padStart(8, '0')}`
}

function fillSlotFormFromSlot(key: SlotKey) {
  const slot = getSlot(key)
  editingSlotKey.value = key
  slotForm.key = key
  slotForm.title = slot.title
  slotForm.model_id = slot.model_id
  slotForm.params = slot.model_id ? paramsFromModel(asrModels.value.find((item) => item.id === slot.model_id), slot.params || {}) : {}
  slotForm.saved_config_hash = slot.saved_config_hash
  slotHotwordsText.value = Array.isArray(slotForm.params.hotwords) ? slotForm.params.hotwords.join('\n') : ''
}

function openHistoryModal(key: SlotKey) {
  fillSlotFormFromSlot(key)
  selectedHistoryPlanId.value = undefined
  selectedHistoryAsrModelId.value = getSlot(key).model_id
  const currentHash = slotConfigHash(getSlot(key))
  const currentPlan = asrPlanList.value.find((plan) => getPlanHash(plan) === currentHash)
  if (currentPlan) selectedHistoryPlanId.value = currentPlan.id
  historyModalOpen.value = true
}

function openConfigModal(key: SlotKey) {
  editingPlan.value = null
  fillSlotFormFromSlot(key)
  configModalOpen.value = true
}

async function saveSlotConfig() {
  if (!slotForm.model_id) {
    message.warning('请选择 ASR 模型')
    return
  }
  if (!String(slotForm.title || '').trim()) {
    message.warning('请填写方案名称，例如：整段无热词 / 整段上下文热词 / 分段无热词')
    return
  }
  const selectedModel = asrModels.value.find((model) => model.id === slotForm.model_id)
  const nextParams = prepareSlotParamsForSave(selectedModel, slotForm.params || {})
  const displayName = String(slotForm.title || '').trim()
  const nextSlot: AsrSlot = {
    key: editingSlotKey.value,
    title: displayName,
    model_id: slotForm.model_id,
    params: cleanParams(nextParams),
  }
  const nextHash = slotConfigHash({ ...nextSlot, saved_config_hash: undefined })

  if (editingPlan.value) {
    const saved = await saveEditedPlan(editingPlan.value, nextSlot, nextHash)
    if (!saved) return
    configModalOpen.value = false
    message.success('历史方案已更新')
    return
  }

  const slot = getSlot(editingSlotKey.value)
  slot.title = nextSlot.title
  slot.model_id = nextSlot.model_id
  slot.params = nextSlot.params
  slot.saved_config_hash = undefined
  await saveSlotPlanToBackend(slot)
  configModalOpen.value = false
  message.success('配置已保存，可直接用于当前 ASR 方案')
}

function prepareSlotParamsForSave(selectedModel: ModelConfig | undefined, params: Record<string, any>) {
  const nextParams = { ...(params || {}) }
  if (selectedModel?.provider === 'volcengine') {
    if (nextParams.context_mode === 'dialog_ctx') {
      delete nextParams.hotwords
    } else {
      nextParams.context_mode = 'hotwords'
      nextParams.hotwords = slotHotwordsText.value.split(/\r?\n|,|，/).map((w) => w.trim()).filter(Boolean)
      delete nextParams.context_text
    }
  }
  return nextParams
}

function editHistoryPlan(plan: AsrPlan) {
  selectedHistoryPlanId.value = plan.id
  editingPlan.value = plan
  editingSlotKey.value = editingSlotKey.value || 'A'
  slotForm.key = editingSlotKey.value
  slotForm.title = planDisplayName(plan)
  slotForm.model_id = plan.model_id
  const model = asrModels.value.find((item) => item.id === plan.model_id)
  slotForm.params = model ? paramsFromModel(model, plan.params || {}) : { ...(plan.params || {}) }
  slotForm.saved_config_hash = getPlanHash(plan)
  slotHotwordsText.value = Array.isArray(slotForm.params.hotwords) ? slotForm.params.hotwords.join('\n') : ''
  configModalOpen.value = true
}

async function saveEditedPlan(plan: AsrPlan, nextSlot: AsrSlot, nextHash: string) {
  if (!nextSlot.model_id) return null
  const oldHash = getPlanHash(plan)
  const duplicatePlan = savedAsrPlans.value.find((item) =>
    getPlanHash(item) === nextHash && item.backend_id && item.backend_id !== plan.backend_id)
  if (duplicatePlan) {
    message.warning(`当前配置与已保存方案“${planDisplayName(duplicatePlan)}”完全一致，请直接使用该方案或调整参数后再保存。`)
    return null
  }
  const payload = {
    name: nextSlot.title,
    asr_model_id: nextSlot.model_id,
    params: cleanParams({ ...(nextSlot.params || {}) }),
    config_hash: nextHash,
  }
  let saved: any
  if (plan.backend_id) {
    saved = await asrOptimizationApi.updatePlan(plan.backend_id, payload)
  } else {
    saved = await asrOptimizationApi.savePlan({
      ...payload,
      source: 'custom',
    })
  }
  const normalized = normalizeBackendPlans([saved])[0]
  savedAsrPlans.value = [
    normalized,
    ...savedAsrPlans.value.filter((item) => item.backend_id !== normalized.backend_id && getPlanHash(item) !== oldHash && getPlanHash(item) !== nextHash),
  ]

  asrSlots.value.forEach((slot) => {
    if (slot.saved_config_hash === oldHash || slot.saved_config_hash === nextHash) {
      slot.title = normalized.title
      slot.model_id = normalized.model_id
      slot.params = cleanParams({ ...(normalized.params || {}) })
      slot.saved_config_hash = normalized.config_hash
    }
  })

  if (selectedHistoryPlanId.value === plan.id) selectedHistoryPlanId.value = normalized.id
  editingPlan.value = null
  return normalized
}

function applySelectedPlanToSlot() {
  const plan = selectedHistoryPlan.value
  if (!plan) return
  applyPlanToSlot(plan)
}

function applyPlanToSlot(plan: AsrPlan) {
  const slot = getSlot(editingSlotKey.value)
  slot.title = plan.title || '历史方案'
  slot.model_id = plan.model_id
  slot.params = cleanParams({ ...(plan.params || {}) })
  slot.saved_config_hash = plan.config_hash
  historyModalOpen.value = false
  message.success('已使用历史方案，已有 ASR 结果会直接显示')
}

function onSlotModelChange() {
  const model = asrModels.value.find((item) => item.id === slotForm.model_id)
  if (!model) return
  slotForm.params = paramsFromModel(model)
  slotHotwordsText.value = Array.isArray(slotForm.params.hotwords) ? slotForm.params.hotwords.join('\n') : ''
}

function paramsFromModel(model?: ModelConfig, overrides: Record<string, any> = {}) {
  if (!model) return { ...(overrides || {}) }
  const merged: Record<string, any> = {
    ...defaultAsrParamsForProvider(model.provider),
    ...(model.params || {}),
    ...(overrides || {}),
  }
  if (model.provider === 'volcengine' && !merged.context_mode) {
    merged.context_mode = merged.context_text ? 'dialog_ctx' : 'hotwords'
  }
  return {
    ...merged,
    use_boosting_table: merged.use_boosting_table !== false,
    use_correct_table: merged.use_correct_table !== false,
    use_context_hotwords: merged.use_context_hotwords !== false,
  }
}

function titleFromVariant(value: string) {
  return String(value || '')
    .replace(/^ASR\s+[AB][-－]/, '')
    .trim() || '历史方案'
}

function getPlanHash(plan: AsrPlan) {
  return plan.config_hash || String(plan.id || '').replace(/^(saved|history):/, '')
}

function planDisplayName(plan: AsrPlan) {
  return String(plan.title || plan.name || '未命名方案').trim() || '未命名方案'
}

function planStats(plan: AsrPlan) {
  const hash = getPlanHash(plan)
  let success = 0
  let failed = 0
  let missing = 0
  filteredRecords.value.forEach((record) => {
    const result = asrResultsByRecord.value[String(record.id)]?.[hash]
    if (result?.status === 'success') success += 1
    else if (result?.status === 'failed') failed += 1
    else missing += 1
  })
  return { success, failed, missing }
}

function planFeatureStatus(plan: AsrPlan, type: 'boosting' | 'correct' | 'hotwords') {
  const params = plan.params || {}
  if (type === 'boosting') {
    const configured = !!(params.boosting_table_id || params.boosting_table_name)
    if (!configured) return '未配置'
    return params.use_boosting_table === false ? '已配置 / 未启用' : '已配置 / 已启用'
  }
  if (type === 'correct') {
    const configured = !!(params.correct_table_id || params.correct_table_name)
    if (!configured) return '未配置'
    return params.use_correct_table === false ? '已配置 / 未启用' : '已配置 / 已启用'
  }
  const count = Array.isArray(params.hotwords) ? params.hotwords.length : 0
  if (!count && !params.context_text) return '未配置'
  const label = params.context_mode === 'dialog_ctx' || (!count && params.context_text) ? '业务上下文' : `热词列表 ${count} 个`
  return params.use_context_hotwords === false ? `${label} / 未启用` : `${label} / 已启用`
}

function formatHotwords(value: any) {
  if (!Array.isArray(value) || !value.length) return '未配置'
  return value.join('\n')
}

const ASR_PLAN_STORAGE_KEY = 'bchao.asrOptimize.savedPlans.v1'

function loadLocalSavedAsrPlans(): AsrPlan[] {
  try {
    const raw = window.localStorage.getItem(ASR_PLAN_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function normalizeBackendPlans(rows: any[]): AsrPlan[] {
  return (rows || []).map((row) => ({
    id: `saved:${row.config_hash}`,
    backend_id: row.id,
    name: row.name,
    model_id: row.asr_model_id,
    title: row.name,
    params: row.params || {},
    config_hash: row.config_hash,
    source: row.source === 'history' ? 'history' : 'custom',
  }))
}

async function migrateLocalPlansToBackend() {
  const localPlans = loadLocalSavedAsrPlans()
  if (!localPlans.length) return
  for (const plan of localPlans) {
    if (!plan.model_id || !getPlanHash(plan)) continue
    try {
      await asrOptimizationApi.savePlan({
        name: planDisplayName(plan),
        asr_model_id: plan.model_id,
        params: cleanParams({ ...(plan.params || {}) }),
        config_hash: getPlanHash(plan),
        source: 'custom',
      })
    } catch {
      // 迁移失败不阻塞主页面，用户下次保存仍会进入后端。
    }
  }
  try {
    window.localStorage.removeItem(ASR_PLAN_STORAGE_KEY)
  } catch {
    // ignore
  }
}

async function saveSlotPlanToBackend(slot: AsrSlot) {
  if (!slot.model_id) return null
  const hash = slotConfigHash({ ...slot, saved_config_hash: undefined })
  const displayName = String(slot.title || '自定义方案').trim() || '自定义方案'
  const saved: any = await asrOptimizationApi.savePlan({
    name: displayName,
    asr_model_id: slot.model_id,
    params: cleanParams({ ...(slot.params || {}) }),
    config_hash: hash,
    source: 'custom',
  })
  const normalized = normalizeBackendPlans([saved])[0]
  const index = savedAsrPlans.value.findIndex((item) => getPlanHash(item) === hash)
  if (index >= 0) savedAsrPlans.value[index] = normalized
  else savedAsrPlans.value.unshift(normalized)
  return normalized
}

async function deleteSavedPlan(plan: AsrPlan) {
  const hash = getPlanHash(plan)
  if (!hash) {
    message.warning('该方案缺少配置指纹，无法删除')
    return
  }
  const result: any = await asrOptimizationApi.deletePlanByHash(hash)
  savedAsrPlans.value = savedAsrPlans.value.filter((item) => getPlanHash(item) !== hash)
  asrHistoryRows.value = asrHistoryRows.value.filter((row) => row.config_hash !== hash)
  Object.values(asrResultsByRecord.value).forEach((recordMap) => {
    delete recordMap[hash]
  })
  asrSlots.value.forEach((slot) => {
    if (slot.saved_config_hash === hash) slot.saved_config_hash = undefined
  })
  if (selectedHistoryPlanId.value === plan.id) selectedHistoryPlanId.value = undefined
  await loadLlmResults()
  message.success(`已删除：ASR ${result?.deleted_asr_results || 0} 条，LLM ${result?.deleted_llm_results || 0} 条`)
}

function featureStatus(slot: AsrSlot, type: 'boosting' | 'hotwords') {
  if (type === 'boosting') {
    const configured = !!(slot.params.boosting_table_id || slot.params.boosting_table_name)
    if (!configured) return '未配置'
    return slot.params.use_boosting_table === false ? '已配置 / 未启用' : '已配置 / 已启用'
  }
  const count = Array.isArray(slot.params.hotwords) ? slot.params.hotwords.length : 0
  if (!count && !slot.params.context_text) return '未配置'
  const label = slot.params.context_mode === 'dialog_ctx' || (!count && slot.params.context_text) ? '业务上下文' : `热词列表 ${count} 个`
  return slot.params.use_context_hotwords === false ? `${label} / 未启用` : `${label} / 已启用`
}

async function runActiveSlotAsr(force: boolean) {
  await runSlotsAsr([activeSlotKey.value], force)
}

async function runSlotAsr(key: SlotKey, force: boolean) {
  await runSlotsAsr([key], force)
}

async function runSlotsAsr(keys: SlotKey[], force: boolean) {
  const scopeRecords = asrExecutionRecords.value
  if (!selectedAsrRowKeys.value.length) {
    message.warning('执行 ASR 前请先勾选需要处理的检查记录，避免误全量消耗')
    return
  }
  asrRunning.value = true
  asrProgress.value = ''
  asrTotal.value = 0
  asrCompleted.value = 0
  asrFailedCount.value = 0
  let successCount = 0
  let failedCount = 0
  let skippedCount = 0
  try {
    const tasks: Array<{ record: PatientExamination; slot: AsrSlot }> = []
    scopeRecords.forEach((record) => {
      keys.forEach((key) => {
        const slot = getSlot(key)
        if (!slot.model_id) {
          skippedCount += 1
          appendAsrLog('warning', `${record.record_id} / ASR ${slot.key} 跳过：未选择模型`)
          return
        }
        if (!force && isUsableAsrResult(getAsrResult(record, slot))) {
          skippedCount += 1
          appendAsrLog('info', `${record.record_id} / ASR ${slot.key} 跳过：已有成功结果`)
          return
        }
        tasks.push({ record, slot })
      })
    })
    if (!tasks.length) {
      message.info(selectedAsrRowKeys.value.length ? '选中记录没有需要补齐的 ASR 任务' : '当前筛选范围没有需要补齐的 ASR 任务')
      return
    }
    asrTotal.value = tasks.length
    appendAsrLog('info', `开始执行 ${keys.map((key) => `ASR ${key}`).join('、')}：共 ${tasks.length} 条，${force ? '重跑' : '补齐'}`)
    for (let i = 0; i < tasks.length; i += 1) {
      const task = tasks[i]
      asrProgress.value = `${i + 1}/${tasks.length} ${task.record.record_id} / ASR ${task.slot.key}`
      try {
        appendAsrLog('info', `${task.record.record_id} / ASR ${task.slot.key} 启动：${slotDisplayName(task.slot)}`)
        await runOneAsr(task.record, task.slot)
        successCount += 1
        appendAsrLog('success', `${task.record.record_id} / ASR ${task.slot.key} 转写成功`)
      } catch (error: any) {
        failedCount += 1
        asrFailedCount.value = failedCount
        appendAsrLog('error', `${task.record.record_id} / ASR ${task.slot.key} 转写失败：${error?.message || error || '未知错误'}`)
        message.error(`${task.record.record_id} / ASR ${task.slot.key} 失败：${error?.message || error || '未知错误'}`)
      } finally {
        asrCompleted.value += 1
      }
    }
    await loadAsrResults()
    if (failedCount) {
      message.warning(`ASR 执行完成：成功 ${successCount} 条，失败 ${failedCount} 条，跳过 ${skippedCount} 条`)
      appendAsrLog('warning', `ASR 执行完成：成功 ${successCount} 条，失败 ${failedCount} 条，跳过 ${skippedCount} 条`)
    } else {
      message.success(`ASR 执行完成：成功 ${successCount} 条，跳过 ${skippedCount} 条`)
      appendAsrLog('success', `ASR 执行完成：成功 ${successCount} 条，跳过 ${skippedCount} 条`)
    }
  } finally {
    asrRunning.value = false
    asrProgress.value = ''
  }
}

function appendAsrLog(level: AsrLogLine['level'], messageText: string) {
  const now = new Date()
  asrLogs.value.unshift({
    id: Date.now() + Math.random(),
    time: now.toLocaleTimeString('zh-CN', { hour12: false }),
    level,
    message: messageText,
  })
  if (asrLogs.value.length > 300) asrLogs.value = asrLogs.value.slice(0, 300)
}

function clearAsrLogs() {
  asrLogs.value = []
  asrTotal.value = 0
  asrCompleted.value = 0
  asrFailedCount.value = 0
}

function runOneAsr(record: PatientExamination, slot: AsrSlot): Promise<AsrResult> {
  if (!slot.model_id) return Promise.reject(new Error('ASR 模型未选择'))
  return new Promise(async (resolve, reject) => {
    try {
      const started: any = await patientApi.startAsrTask(record.id, {
        asr_model_id: slot.model_id!,
        variant_name: slotVariantName(slot),
        params_override: slot.params,
        source: 'asr_optimization',
        experiment_key: experimentKey(),
        config_hash: slotConfigHash(slot),
      })
      const resultId = started?.result_id || started?.id
      if (!resultId) throw new Error('ASR 任务启动失败')
      appendAsrLog('info', `${record.record_id} / ASR ${slot.key} 后台任务启动成功：#${resultId}`)
      const startedAt = Date.now()
      while (Date.now() - startedAt < 30 * 60 * 1000) {
        await new Promise((r) => window.setTimeout(r, 2500))
        const current: any = await patientApi.getAsrTask(record.id, resultId)
        if (current?.status === 'success' || current?.status === 'partial') {
          resolve(current as AsrResult)
          return
        }
        if (current?.status === 'failed') throw new Error(current.error_message || 'ASR 调用失败')
      }
      throw new Error('ASR 后台任务超时')
    } catch (e) {
      reject(e)
    }
  })
}

async function runBatchLlm() {
  if (!selectedTemplateId.value || !selectedLlmModelId.value) return
  llmRunning.value = true
  llmProgress.value = ''
  try {
    const template = promptTemplates.value.find((item: any) => item.id === selectedTemplateId.value)
    const rows = structuredRows.value
    let executedCount = 0
    let skippedNoAsrCount = 0
    for (let i = 0; i < rows.length; i += 1) {
      const row = rows[i]
      const asr = getAsrResult(records.value.find((r) => r.id === row.patient_id)!, activeSlot.value)
      if (!asr?.id || asr.status !== 'success') {
        skippedNoAsrCount += 1
        continue
      }
      llmProgress.value = `${i + 1}/${rows.length} ${row.record_id}`
      await patientApi.runLlm(row.patient_id, {
        llm_model_id: selectedLlmModelId.value,
        asr_result_id: asr.id,
        prompt_template_id: selectedTemplateId.value,
        prompt_content: template?.content,
        source: 'asr_optimization',
        experiment_key: experimentKey(),
      })
      executedCount += 1
    }
    if (!executedCount) {
      message.warning(`当前筛选范围没有可用于 LLM 的成功 ASR 结果，跳过 ${skippedNoAsrCount} 条。请确认上方当前选中的 ASR 方案与刚跑成功的方案一致。`)
      return
    }
    await loadLlmResults()
    message.success(`LLM 批量执行完成：成功发起 ${executedCount} 条，跳过无 ASR ${skippedNoAsrCount} 条`)
  } finally {
    llmRunning.value = false
    llmProgress.value = ''
  }
}

function pickLlmForAsr(record: PatientExamination, asrResultId?: number) {
  if (!asrResultId) return null
  const rows = llmResultsByRecord.value[String(record.id)] || []
  let candidates = rows.filter((row) => row.asr_result_id === asrResultId)
  if (selectedTemplateId.value) {
    candidates = candidates.filter((row) => Number(row.prompt_template_id) === Number(selectedTemplateId.value))
  }
  if (selectedLlmModelId.value) {
    candidates = candidates.filter((row) => Number(row.llm_model_id) === Number(selectedLlmModelId.value))
  }
  return candidates
    .sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())[0] || null
}

function getGroupMatchStatus(record: PatientExamination, llm: any, field: any): MatchStatus {
  if (!llm || !record.result) return 'empty'
  const structured = llm.structured_result || llm.structured || {}
  const statuses = field.fields.map((fieldKey: string) => {
    return compareFieldValue(structured, record.result, fieldKey)
  })
  return statuses.every((s: MatchStatus) => s === 'match') ? 'match' : statuses.every((s: MatchStatus) => s === 'empty') ? 'empty' : 'mismatch'
}

function getGroupIssueText(record: PatientExamination, llm: any, field: any): string {
  if (!llm || !record.result) return ''
  const structured = llm.structured_result || llm.structured || {}
  if (field.key === 'right_follicle' || field.key === 'left_follicle') {
    const side = field.key === 'right_follicle' ? 'right' : 'left'
    const llmList = normalizeFollicles(structured?.[`${side}_follicles`])
    const gtList = normalizeFollicles((record.result as any)?.[`${side}_follicles`])
    const diff = diffFollicles(gtList, llmList)
    const total = gtList.reduce((sum, item) => sum + item.count, 0)
    const matched = Math.max(0, total - diff.missing.reduce((sum, item) => sum + item.count, 0))
    const rate = total ? `${((matched / total) * 100).toFixed(1)}%` : '-'
    const parts = [`${rate}`]
    if (diff.missing.length) parts.push(`漏:${formatFollicleDiff(diff.missing)}`)
    if (diff.extra.length) parts.push(`多:${formatFollicleDiff(diff.extra)}`)
    return parts.join('；')
  }
  const mismatch = field.fields.find((fieldKey: string) => compareFieldValue(structured, record.result, fieldKey) === 'mismatch')
  if (!mismatch) return ''
  return `提取:${formatFieldValue(structured?.[mismatch])} / 真实:${formatFieldValue((record.result as any)?.[mismatch])}`
}

function optimizationMarkKey(llmResultId?: number, fieldGroup?: string, fieldKey?: string) {
  return `${llmResultId || 0}:${fieldGroup || ''}:${fieldKey || ''}`
}

function getOptimizationMark(llmResultId?: number, fieldGroup?: string) {
  if (!llmResultId || !fieldGroup) return null
  return optimizationMarksByKey.value[optimizationMarkKey(llmResultId, fieldGroup)] || null
}

function buildAttributionRow(row: any, field: any) {
  const llm = row.llm
  const mark = getOptimizationMark(llm?.id, field.key)
  const baseStatus = row.field_status[field.key]
  const status = getAttributionStatus(baseStatus, mark)
  const statStatus = getStatAttributionStatus(row, field.key)
  const reason = getAttributionReason(row, field, status, mark)
  return {
    key: `${row.patient_id}-${llm?.id || 'none'}-${field.key}`,
    patient_id: row.patient_id,
    record_id: row.record_id,
    date: row.date,
    field: field.label,
    group: field.key,
    status,
    stat_status: statStatus,
    attribution_level: getAttributionLevel(field, status, mark),
    error_type: getAttributionErrorType(field, status, mark),
    reason,
    has_mark: !!mark,
    mark,
    llm,
    llm_result_id: llm?.id,
    asr_result_id: llm?.asr_result_id,
    asr_config_hash: getAsrResult(row.record, activeSlot.value)?.config_hash || slotConfigHash(activeSlot.value),
    asr_slot: row.asr_slot,
    prompt_template: llm?.prompt_template_name || '-',
  }
}

function buildAnalysisStructuredRow(record: PatientExamination, llm: any) {
  const fieldStatus: Record<string, MatchStatus> = {}
  const fieldNotes: Record<string, string> = {}
  fieldColumns.forEach((field) => {
    fieldStatus[field.key] = getGroupMatchStatus(record, llm, field)
    fieldNotes[field.key] = getGroupIssueText(record, llm, field)
  })
  const asr = findAsrResultById(llm?.asr_result_id)
  const row = {
    patient_id: record.id,
    record_id: record.record_id,
    date: record.date,
    has_result: !!record.result,
    field_status: fieldStatus,
    field_notes: fieldNotes,
    llm,
    record,
    asr_result: asr,
    asr_label: asrDisplayLabel(asr, llm),
    prompt_label: llm?.prompt_template_name || getPromptTemplateName(Number(llm?.prompt_template_id)),
    llm_label: llm?.full_model_name || llm?.model_name || llm?.llm_model_name || getModelName(Number(llm?.llm_model_id)),
  }
  return {
    ...row,
    accuracy: calculateStructuredRowAccuracy(row),
  }
}

function findAsrResultById(id?: number) {
  if (!id) return null
  const target = Number(id)
  return asrHistoryRows.value.find((row) => Number(row.id) === target) || null
}

function asrDisplayLabel(asr: AsrResult | null, llm: any) {
  const snapshot = asr?.config_snapshot || {}
  const variantName = titleFromVariant(snapshot?.variant_name || '')
  const modelName = asr?.model_name || asr?.asr_model_name || llm?.asr_model_name || (asr?.asr_model_id ? getModelName(asr.asr_model_id) : 'ASR')
  const hash = asr?.config_hash ? `·${String(asr.config_hash).slice(0, 8)}` : ''
  return variantName ? `${variantName}${hash}` : `${modelName}${hash}`
}

function chartGroupInfo(row: any) {
  const prompt = row.prompt_label || '未命名提示词'
  const llm = row.llm_label || '未命名LLM'
  const label = `${prompt} / ${llm}`
  return {
    key: `combo:${row.llm?.prompt_template_id || prompt}:${row.llm?.llm_model_id || llm}`,
    label,
    shortLabel: compactChartLabel(label),
  }
}

function aggregateChartFieldRate(rows: any[], field: any) {
  if (field.type === 'follicle') {
    const scores = rows
      .filter((row) => getAttributionStatus(row.field_status[field.group], getRowFieldMark(row, field.group)) !== '排除')
      .map((row) => follicleDetailScore(row, field.subKey))
    const rateSum = scores.reduce((sum, item) => sum + Number(item.rate || 0), 0)
    return {
      total: scores.length,
      matched: Number(rateSum.toFixed(2)),
      rate: scores.length ? rateSum / scores.length : 1,
    }
  }
  const denominator = rows.filter((row) => getAttributionStatus(row.field_status[field.key], getRowFieldMark(row, field.key)) !== '排除').length
  const matched = rows.filter((row) => getStatAttributionStatus(row, field.key) === '正确').length
  return {
    total: denominator,
    matched,
    rate: denominator ? matched / denominator : 1,
  }
}

function percentWidth(value?: number | null) {
  const n = Math.max(0, Math.min(1, Number(value ?? 0)))
  return `${(n * 100).toFixed(1)}%`
}

function heatmapColor(value?: number | null) {
  if (value == null || !Number.isFinite(Number(value))) return '#f5f5f5'
  const rate = Math.max(0, Math.min(1, Number(value)))
  if (rate >= 0.95) return '#d9f7be'
  if (rate >= 0.8) return '#f6ffed'
  if (rate >= 0.6) return '#fff7e6'
  return '#fff1f0'
}

function compactChartLabel(value: string) {
  const text = String(value || '-').trim()
  return text.length > 18 ? `${text.slice(0, 17)}…` : text
}

function getFieldDefinition(fieldKey: string) {
  return fieldColumns.find((field) => field.key === fieldKey)
}

function getRowFieldMark(row: any, fieldKey: string): OptimizationFieldReviewMark | null {
  const mark = getOptimizationMark(row?.llm?.id, fieldKey)
  // 如果当前真实 B 超值/结构化结果已经重新匹配，历史异常/排除标记视为失效，
  // 避免出现“准确率 100%，字段仍显示异常”的错位。
  if (mark && row?.field_status?.[fieldKey] === 'match') return null
  return mark
}

function calculateStructuredRowAccuracy(row: any) {
  if (!row?.llm || !row?.has_result) return null
  let correct = 0
  let denominator = 0
  fieldColumns.forEach((field) => {
    const status = getAttributionStatus(row.field_status[field.key], getRowFieldMark(row, field.key))
    if (status === '排除') return
    denominator += 1
    if (getStatAttributionStatus(row, field.key) === '正确') correct += 1
  })
  return denominator ? correct / denominator : 1
}

function getStatAttributionStatus(row: any, fieldKey: string) {
  const mark = getRowFieldMark(row, fieldKey)
  const displayStatus = getAttributionStatus(row?.field_status?.[fieldKey] || 'empty', mark)
  if (displayStatus === '排除' || displayStatus === '异常') return displayStatus
  if (isGroupStatMatch(row, fieldKey)) return '正确'
  return displayStatus
}

function isGroupStatMatch(row: any, fieldKey: string) {
  const field = getFieldDefinition(fieldKey)
  if (!field) return false
  return field.fields.every((subKey: string) => isSubFieldStatMatch(row, subKey))
}

function isSubFieldStatMatch(row: any, subKey: string) {
  const llm = row?.llm
  const structured = llm?.structured_result || llm?.structured || {}
  const result = row?.record?.result || {}
  return compareFieldValueForStats(structured, result, subKey) === 'match'
}

function follicleDetailScore(row: any, subKey: string) {
  const llm = row?.llm
  const structured = llm?.structured_result || llm?.structured || {}
  const result = row?.record?.result || {}
  const gtList = normalizeFollicles(result?.[subKey])
  const llmList = normalizeFollicles(structured?.[subKey])
  const gtTotal = gtList.reduce((sum, item) => sum + item.count, 0)
  const llmTotal = llmList.reduce((sum, item) => sum + item.count, 0)
  if (!gtTotal && !llmTotal) return { matched: 1, total: 1, rate: 1 }
  const gtMap = follicleCountMap(gtList)
  const llmMap = follicleCountMap(llmList)
  const matched = Object.entries(gtMap).reduce((sum, [size, count]) => {
    return sum + Math.min(count, llmMap[size] || 0)
  }, 0)
  const total = Math.max(gtTotal, llmTotal)
  return { matched, total, rate: total ? matched / total : 1 }
}

function fieldDisplayColor(row: any, fieldKey: string) {
  const mark = getRowFieldMark(row, fieldKey)
  if (mark?.mark_type === 'exclude') return 'orange'
  if (mark?.mark_type === 'mismatch_note') return 'red'
  return matchColor(row?.field_status?.[fieldKey] || 'empty')
}

function fieldDisplayText(row: any, fieldKey: string) {
  const mark = getRowFieldMark(row, fieldKey)
  if (mark?.mark_type === 'exclude') return '⚠️ 排除'
  if (mark?.mark_type === 'mismatch_note') return '❌ 异常'
  return matchText(row?.field_status?.[fieldKey] || 'empty')
}

function getFieldDisplayNote(row: any, fieldKey: string) {
  const mark = getRowFieldMark(row, fieldKey)
  const manual = [mark?.reason, mark?.note].filter(Boolean).join('；')
  const detail = row?.field_notes?.[fieldKey] || ''
  if (manual && detail) return `${manual}；${detail}`
  return manual || detail
}

function getSubFieldStatus(row: any, fieldKey: string): MatchStatus {
  const llm = row?.llm
  return compareFieldValue(llm?.structured_result || llm?.structured || {}, row?.record?.result || {}, fieldKey)
}

function businessSubFields(fieldKey: string) {
  if (fieldKey === 'right_follicle') {
    return [
      { key: 'right_follicle_total', label: '右卵泡总数' },
      { key: 'right_follicles', label: '右卵泡明细' },
    ]
  }
  if (fieldKey === 'left_follicle') {
    return [
      { key: 'left_follicle_total', label: '左卵泡总数' },
      { key: 'left_follicles', label: '左卵泡明细' },
    ]
  }
  if (fieldKey === 'right_ovary') {
    return [
      { key: 'right_ovary_length', label: '右卵巢长' },
      { key: 'right_ovary_width', label: '右卵巢宽' },
    ]
  }
  if (fieldKey === 'left_ovary') {
    return [
      { key: 'left_ovary_length', label: '左卵巢长' },
      { key: 'left_ovary_width', label: '左卵巢宽' },
    ]
  }
  const field = getFieldDefinition(fieldKey)
  return [{ key: fieldKey, label: field?.label || fieldKey }]
}

function getBusinessFieldCompareRows(row: any, fieldKey: string) {
  const structured = row?.llm?.structured_result || row?.llm?.structured || {}
  const gt = row?.record?.result || {}
  return businessSubFields(fieldKey).map((field) => ({
    key: field.key,
    label: field.label,
    status: getSubFieldStatus(row, field.key),
    llmValue: structured?.[field.key],
    gtValue: gt?.[field.key],
    llmText: formatCompareValue(structured?.[field.key]),
    gtText: formatCompareValue(gt?.[field.key]),
  }))
}

function getFieldDifferenceSummary(row: any, fieldKey: string) {
  const mark = getRowFieldMark(row, fieldKey)
  const manual = [mark?.reason, mark?.note].filter(Boolean).join('；')
  if (mark?.mark_type === 'exclude') return manual ? `已人工排除：${manual}` : '已人工排除：该字段不纳入当前准确率统计'
  if (mark?.mark_type === 'mismatch_note') return manual ? `已标记异常：${manual}` : '已标记异常：该字段继续计入不匹配'

  const status = row?.field_status?.[fieldKey] || 'empty'
  if (status === 'match') return `${getFieldLabel(fieldKey)} 完全匹配`
  if (status === 'empty') return `${getFieldLabel(fieldKey)} 暂无可比对结果：可能缺少 LLM 结果或真实 B 超数据`

  const structured = row?.llm?.structured_result || row?.llm?.structured || {}
  const gt = row?.record?.result || {}
  if (fieldKey === 'right_follicle' || fieldKey === 'left_follicle') {
    const side = fieldKey === 'right_follicle' ? 'right' : 'left'
    const diff = diffFollicles(
      normalizeFollicles(gt?.[`${side}_follicles`]),
      normalizeFollicles(structured?.[`${side}_follicles`]),
    )
    const parts = []
    const totalStatus = getSubFieldStatus(row, `${side}_follicle_total`)
    if (totalStatus === 'mismatch') {
      parts.push(`总数不一致：LLM ${formatCompareValue(structured?.[`${side}_follicle_total`])} / 真实 ${formatCompareValue(gt?.[`${side}_follicle_total`])}`)
    }
    if (diff.missing.length) parts.push(`漏识别：${formatFollicleDiff(diff.missing)}`)
    if (diff.extra.length) parts.push(`多识别：${formatFollicleDiff(diff.extra)}`)
    return parts.length ? parts.join('；') : `${getFieldLabel(fieldKey)} 不匹配，请查看下方子项差异`
  }

  const diffs = getBusinessFieldCompareRows(row, fieldKey)
    .filter((item) => item.status === 'mismatch')
    .map((item) => `${item.label}：LLM ${item.llmText} / 真实 ${item.gtText}`)
  return diffs.length ? diffs.join('；') : `${getFieldLabel(fieldKey)} 不匹配，请查看下方子项差异`
}

function getAllBusinessCompareRows(row: any) {
  return fieldColumns.flatMap((field) => getBusinessFieldCompareRows(row, field.key))
}

function getMismatchBusinessCompareRows(row: any) {
  return getAllBusinessCompareRows(row).filter((item) => item.status === 'mismatch')
}

function formatCompareValue(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) {
    const follicles = normalizeFollicles(value)
    if (follicles.length) return follicles.map((item) => `${item.size}×${item.count}`).join('、')
    return value.map((item) => typeof item === 'object' ? JSON.stringify(item) : String(item)).join('、')
  }
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

function getActiveAsrResult(row: any) {
  return row?.record ? getAsrResult(row.record, activeSlot.value) : null
}

function getAudioSegmentRows(row: any) {
  return (row?.record?.segs || []).map((seg: any, index: number) => ({
    key: seg.id || `${row.patient_id}-${index}`,
    seg_index: seg.seg_index ?? index + 1,
    filename: seg.filename || seg.file_name || '-',
    duration: seg.duration ? `${Number(seg.duration).toFixed(1)}s` : '-',
    file_size: formatFileSize(seg.file_size),
  }))
}

function formatFileSize(size?: number) {
  const n = Number(size || 0)
  if (!n) return '-'
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${n} B`
}

function getStructuredDetailMark() {
  const row = fieldDetailRow.value || structuredDetailRow.value
  const fieldKey = fieldDetailField.value || structuredDetailField.value
  if (!row || !fieldKey) return null
  return getRowFieldMark(row, fieldKey)
}

function prepareStructuredMarkForm(row: any, fieldKey: string) {
  const mark = getRowFieldMark(row, fieldKey)
  attributionMarkForm.mark_type = mark?.mark_type || 'exclude'
  attributionMarkForm.reason = mark?.reason || ''
  attributionMarkForm.note = mark?.note || ''
}

async function saveStructuredDetailMark() {
  const row = fieldDetailRow.value || structuredDetailRow.value
  const fieldKey = fieldDetailField.value || structuredDetailField.value
  if (!row?.llm?.id || !fieldKey) {
    message.warning('该记录还没有 LLM 结果，无法标记')
    return
  }
  attributionMarkSaving.value = true
  try {
    const mark = await asrOptimizationApi.saveFieldReviewMark({
      patient_id: row.patient_id,
      field_group: fieldKey,
      asr_config_hash: getActiveAsrResult(row)?.config_hash || slotConfigHash(activeSlot.value),
      asr_result_id: getActiveAsrResult(row)?.id || row.llm?.asr_result_id,
      llm_result_id: row.llm.id,
      mark_type: attributionMarkForm.mark_type,
      reason: attributionMarkForm.reason || null,
      note: attributionMarkForm.note || null,
    }) as OptimizationFieldReviewMark
    optimizationMarksByKey.value = {
      ...optimizationMarksByKey.value,
      [optimizationMarkKey(mark.llm_result_id, mark.field_group, mark.field_key || undefined)]: mark,
    }
    message.success('字段标记已保存')
  } finally {
    attributionMarkSaving.value = false
  }
}

async function clearStructuredDetailMark() {
  const row = fieldDetailRow.value || structuredDetailRow.value
  const fieldKey = fieldDetailField.value || structuredDetailField.value
  if (!row?.llm?.id || !fieldKey) return
  await asrOptimizationApi.clearFieldReviewMark(row.llm.id, fieldKey)
  const next = { ...optimizationMarksByKey.value }
  delete next[optimizationMarkKey(row.llm.id, fieldKey)]
  optimizationMarksByKey.value = next
  prepareStructuredMarkForm(row, fieldKey)
  message.success('字段标记已清除')
}

function getAttributionStatus(status: MatchStatus, mark: OptimizationFieldReviewMark | null) {
  if (mark?.mark_type === 'exclude') return '排除'
  if (mark?.mark_type === 'mismatch_note') return '异常'
  if (status === 'match') return '正确'
  if (status === 'empty') return '未提取'
  return '错误'
}

function getAttributionLevel(field: any, status: string, mark: OptimizationFieldReviewMark | null) {
  if (status === '正确') return '—'
  if (status === '未提取') return '数据缺失'
  const text = `${mark?.reason || ''}${mark?.note || ''}`.toLowerCase()
  if (mark?.mark_type === 'exclude') {
    if (text.includes('asr') || text.includes('收音') || text.includes('录音')) return 'ASR/收音'
    return '人工排除'
  }
  if (mark?.mark_type === 'mismatch_note') return '人工标记'
  if (field.key === 'right_follicle' || field.key === 'left_follicle') return 'ASR/LLM'
  return 'LLM提取'
}

function getAttributionErrorType(field: any, status: string, mark: OptimizationFieldReviewMark | null) {
  if (status === '正确') return '—'
  if (status === '未提取') return '缺少结果'
  if (mark?.reason) return mark.reason
  if (status === '排除') return '人工排除'
  if (status === '异常') return '人工异常'
  return `${field.label}不一致`
}

function getAttributionReason(row: any, field: any, status: string, mark: OptimizationFieldReviewMark | null) {
  if (status === '正确') return '字段正确'
  const manual = [mark?.reason, mark?.note].filter(Boolean).join('；')
  const detail = row.field_notes[field.key] || ''
  if (manual && detail) return `${manual}；${detail}`
  if (manual) return manual
  if (detail) return detail
  if (status === '未提取') return '缺少 LLM 提取结果或真实 B 超数据'
  return 'LLM 提取结果与真实 B 超结果不一致'
}

function attributionStatusColor(status: string) {
  if (status === '正确') return 'green'
  if (status === '排除') return 'orange'
  if (status === '未提取') return 'default'
  return 'red'
}

function resetAttributionFilters() {
  attributionFieldFilter.value = undefined
  attributionStatusFilter.value = undefined
  attributionOnlyMarked.value = false
}

function openAttributionMark(row: any) {
  if (!row.llm_result_id) {
    message.warning('该记录还没有 LLM 结果，无法标记')
    return
  }
  attributionMarkRow.value = row
  attributionMarkForm.mark_type = row.mark?.mark_type || 'exclude'
  attributionMarkForm.reason = row.mark?.reason || ''
  attributionMarkForm.note = row.mark?.note || ''
  attributionMarkOpen.value = true
}

async function saveAttributionMark() {
  const row = attributionMarkRow.value
  if (!row?.llm_result_id) return
  attributionMarkSaving.value = true
  try {
    const mark = await asrOptimizationApi.saveFieldReviewMark({
      patient_id: row.patient_id,
      field_group: row.group,
      asr_config_hash: row.asr_config_hash,
      asr_result_id: row.asr_result_id,
      llm_result_id: row.llm_result_id,
      mark_type: attributionMarkForm.mark_type,
      reason: attributionMarkForm.reason || null,
      note: attributionMarkForm.note || null,
    }) as OptimizationFieldReviewMark
    optimizationMarksByKey.value = {
      ...optimizationMarksByKey.value,
      [optimizationMarkKey(mark.llm_result_id, mark.field_group, mark.field_key || undefined)]: mark,
    }
    attributionMarkOpen.value = false
    message.success('归因标记已保存')
  } finally {
    attributionMarkSaving.value = false
  }
}

async function clearAttributionMark(row: any) {
  if (!row?.llm_result_id) return
  await asrOptimizationApi.clearFieldReviewMark(row.llm_result_id, row.group)
  const next = { ...optimizationMarksByKey.value }
  delete next[optimizationMarkKey(row.llm_result_id, row.group)]
  optimizationMarksByKey.value = next
  message.success('归因标记已清除')
}

function compareFieldValue(structured: any, gt: any, key: string): MatchStatus {
  const a = structured?.[key]
  const b = gt?.[key]
  if (a == null && b == null) return 'empty'
  if (a == null || b == null) return 'mismatch'
  return JSON.stringify(normalizeValue(a)) === JSON.stringify(normalizeValue(b)) ? 'match' : 'mismatch'
}

function compareFieldValueForStats(structured: any, gt: any, key: string): MatchStatus {
  const status = compareFieldValue(structured, gt, key)
  return status === 'empty' ? 'match' : status
}

function normalizeValue(value: any) {
  if (Array.isArray(value)) return value.map((item) => typeof item === 'object' ? item : String(item)).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)))
  if (typeof value === 'string') return value.trim().toUpperCase()
  return value
}

function normalizeFollicles(value: any): { size: string; count: number }[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (typeof item === 'number' || typeof item === 'string') return { size: normalizeNumberText(item), count: 1 }
      return { size: normalizeNumberText(item?.size), count: Number(item?.count || 1) }
    })
    .filter((item) => item.size)
    .sort((a, b) => Number(a.size) - Number(b.size))
}

function normalizeNumberText(value: any) {
  if (value === null || value === undefined || value === '') return ''
  const n = Number(String(value).replace(/[^\d.]/g, ''))
  if (!Number.isFinite(n)) return String(value)
  return n.toFixed(1)
}

function diffFollicles(gt: { size: string; count: number }[], llm: { size: string; count: number }[]) {
  const gtMap = follicleCountMap(gt)
  const llmMap = follicleCountMap(llm)
  const missing: { size: string; count: number }[] = []
  const extra: { size: string; count: number }[] = []
  Object.entries(gtMap).forEach(([size, count]) => {
    const delta = count - (llmMap[size] || 0)
    if (delta > 0) missing.push({ size, count: delta })
  })
  Object.entries(llmMap).forEach(([size, count]) => {
    const delta = count - (gtMap[size] || 0)
    if (delta > 0) extra.push({ size, count: delta })
  })
  return { missing, extra }
}

function follicleCountMap(items: { size: string; count: number }[]) {
  return items.reduce<Record<string, number>>((acc, item) => {
    acc[item.size] = (acc[item.size] || 0) + item.count
    return acc
  }, {})
}

function formatFollicleDiff(items: { size: string; count: number }[]) {
  return items.map((item) => `${item.size}*${item.count}`).join('、')
}

function defaultAsrParams() {
  return {
    audio_input_mode: 'segments',
    endpoint_mode: 'bigmodel_nostream',
    result_type: 'full',
    enable_itn: true,
    enable_punc: true,
    enable_ddc: false,
    show_utterances: false,
    enable_nonstream: false,
    stream: false,
    use_boosting_table: true,
    use_correct_table: true,
    use_context_hotwords: true,
    context_mode: 'hotwords',
  }
}

function defaultAsrParamsForProvider(provider?: string): Record<string, any> {
  if (provider === 'mimo') {
    return {
      audio_input_mode: 'segments',
      language: 'auto',
      stream: true,
      merge_group_size: 3,
      max_base64_mb: 9.8,
    }
  }
  if (provider === 'volcengine') {
    return defaultAsrParams()
  }
  return {
    audio_input_mode: 'segments',
  }
}

function providerLabel(provider?: string) {
  const map: Record<string, string> = {
    local: '本地',
    mimo: 'MiMo',
    volcengine: '豆包',
    iflytek_rtasr_llm: '讯飞实时转写大模型',
    tencent_speaker_ws: '腾讯实时说话人分离',
    iflytek: '讯飞',
    tencent: '腾讯',
  }
  return provider ? (map[provider] || provider) : '未知'
}

function cleanParams(params: Record<string, any>) {
  const cleaned: Record<string, any> = {}
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    if (Array.isArray(value) && !value.length) return
    if (['end_window_size', 'vad_segment_duration', 'force_to_speech_time'].includes(key)) {
      cleaned[key] = Number(value)
      return
    }
    cleaned[key] = typeof value === 'string' ? value.trim() : value
  })
  return cleaned
}

function compareAsrResultDesc(a: AsrResult, b: AsrResult) {
  const ta = a.created_at ? new Date(a.created_at).getTime() : 0
  const tb = b.created_at ? new Date(b.created_at).getTime() : 0
  if (ta !== tb) return tb - ta
  return (b.id || 0) - (a.id || 0)
}

function getModelName(id: number) {
  return asrModels.value.find((m) => m.id === id)?.name || llmModels.value.find((m) => m.id === id)?.name || `模型${id}`
}

function getPromptTemplateName(id: number) {
  return promptTemplates.value.find((item: any) => Number(item.id) === Number(id))?.name || `提示词${id}`
}

function audioModeText(value: string) {
  if (value === 'segments') return '原始分段'
  if (value === 'grouped') return '分组合并'
  if (value === 'merged') return '整段合并'
  return value
}

function endpointModeText(value: string) {
  if (value === 'bigmodel_nostream') return 'nostream'
  if (value === 'bigmodel_async') return 'async'
  if (value === 'bigmodel') return '双向'
  return value
}

function normalizeTranscript(text: string) {
  return String(text || '').replace(/\s+/g, ' ').trim()
}

type TranscriptDiffSegment = {
  text: string
  changed: boolean
}

type TranscriptDiffToken = {
  text: string
  key: string
  significant: boolean
}

function diffTranscriptSegments(aText: string, bText: string) {
  if (!aText && !bText) return { a: [] as TranscriptDiffSegment[], b: [] as TranscriptDiffSegment[] }
  if (aText === bText) {
    return {
      a: [{ text: aText, changed: false }],
      b: [{ text: bText, changed: false }],
    }
  }

  const aTokens = tokenizeTranscriptForDiff(aText)
  const bTokens = tokenizeTranscriptForDiff(bText)
  const aSignificant = aTokens.filter((token) => token.significant)
  const bSignificant = bTokens.filter((token) => token.significant)

  if (!aSignificant.length || !bSignificant.length) {
    return {
      a: mergeDiffSegments(aTokens.map((token) => ({ text: token.text, changed: token.significant && !!bSignificant.length }))),
      b: mergeDiffSegments(bTokens.map((token) => ({ text: token.text, changed: token.significant && !!aSignificant.length }))),
    }
  }

  const { aMatched, bMatched } = lcsMatchedTokenIndexes(
    aSignificant.map((token) => token.key),
    bSignificant.map((token) => token.key),
  )

  return {
    a: buildDiffSegments(aTokens, aMatched),
    b: buildDiffSegments(bTokens, bMatched),
  }
}

function tokenizeTranscriptForDiff(text: string): TranscriptDiffToken[] {
  return (String(text || '').match(/\s+|\d+(?:\.\d+)?|[A-Za-z]+|[\u4e00-\u9fff]|./g) || []).map((part) => {
    const key = normalizeDiffToken(part)
    return { text: part, key, significant: !!key }
  })
}

function normalizeDiffToken(token: string) {
  const value = String(token || '').trim()
  if (!value) return ''
  if (/^[，。！？、,.!?;；:："'“”‘’（）()【】\[\]{}<>《》\-—~·…/\\|]+$/.test(value)) return ''
  return value.toLowerCase()
}

function lcsMatchedTokenIndexes(aKeys: string[], bKeys: string[]) {
  const m = aKeys.length
  const n = bKeys.length
  const dp = Array.from({ length: m + 1 }, () => new Uint16Array(n + 1))

  for (let i = 1; i <= m; i += 1) {
    for (let j = 1; j <= n; j += 1) {
      dp[i][j] = aKeys[i - 1] === bKeys[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1])
    }
  }

  const aMatched = new Set<number>()
  const bMatched = new Set<number>()
  let i = m
  let j = n
  while (i > 0 && j > 0) {
    if (aKeys[i - 1] === bKeys[j - 1]) {
      aMatched.add(i - 1)
      bMatched.add(j - 1)
      i -= 1
      j -= 1
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      i -= 1
    } else {
      j -= 1
    }
  }
  return { aMatched, bMatched }
}

function buildDiffSegments(tokens: TranscriptDiffToken[], matchedSignificantIndexes: Set<number>) {
  let significantIndex = -1
  return mergeDiffSegments(tokens.map((token) => {
    if (!token.significant) return { text: token.text, changed: false }
    significantIndex += 1
    return { text: token.text, changed: !matchedSignificantIndexes.has(significantIndex) }
  }))
}

function mergeDiffSegments(segments: TranscriptDiffSegment[]) {
  return segments.reduce<TranscriptDiffSegment[]>((acc, segment) => {
    const last = acc[acc.length - 1]
    if (last && last.changed === segment.changed) {
      last.text += segment.text
    } else {
      acc.push({ ...segment })
    }
    return acc
  }, [])
}

function extractMedicalNumbers(text: string) {
  const normalized = normalizeChineseNumericText(normalizeTranscript(text))
  return (normalized.match(/\d+(?:\.\d+)?/g) || []).map((item) => Number(item).toFixed(item.includes('.') ? 1 : 0))
}

const chineseDigitMap: Record<string, string> = {
  零: '0',
  〇: '0',
  一: '1',
  二: '2',
  两: '2',
  三: '3',
  四: '4',
  五: '5',
  六: '6',
  七: '7',
  八: '8',
  九: '9',
}

function normalizeChineseNumericText(text: string) {
  return String(text || '')
    // 卵巢大小/无回声等尺寸常被识别成“三九乘以二九”，这里归一为 39×29。
    .replace(/([零〇一二两三四五六七八九]{2,3})\s*(?:乘以|乘|x|X|×)\s*([零〇一二两三四五六七八九]{1,3})/g, (_match, left, right) => `${chineseDigitSequenceToNumber(left)}×${chineseDigitSequenceToNumber(right)}`)
    // 卵泡/内膜数字常被识别成“十三点九”“十三点点九”，归一为 13.9。
    .replace(/([零〇一二两三四五六七八九十]{1,4})点点?([零〇一二两三四五六七八九])/g, (_match, left, right) => `${chineseNumberToArabic(left)}.${chineseDigitSequenceToNumber(right)}`)
}

function chineseDigitSequenceToNumber(text: string) {
  return String(text || '').split('').map((ch) => chineseDigitMap[ch] ?? ch).join('')
}

function chineseNumberToArabic(text: string) {
  const value = String(text || '')
  if (!value) return ''
  if (!value.includes('十')) return chineseDigitSequenceToNumber(value)
  const [left, right] = value.split('十')
  const tens = left ? Number(chineseDigitSequenceToNumber(left)) : 1
  const ones = right ? Number(chineseDigitSequenceToNumber(right)) : 0
  return String(tens * 10 + ones)
}

function diffNumbers(base: string[], current: string[]) {
  const b = countItems(base)
  const c = countItems(current)
  const missing: string[] = []
  const extra: string[] = []
  Object.entries(b).forEach(([v, n]) => { for (let i = 0; i < n - (c[v] || 0); i += 1) missing.push(v) })
  Object.entries(c).forEach(([v, n]) => { for (let i = 0; i < n - (b[v] || 0); i += 1) extra.push(v) })
  return { missing, extra }
}

function countItems(items: string[]) {
  return items.reduce<Record<string, number>>((acc, item) => {
    acc[item] = (acc[item] || 0) + 1
    return acc
  }, {})
}

function textDiff(a: string, b: string) {
  if (!a && !b) return { rate: 0, changed: false }
  if (a === b) return { rate: 0, changed: false }
  const rate = Math.abs(a.length - b.length) / Math.max(a.length, b.length, 1)
  return { rate: Math.max(rate, a.slice(0, 1000) === b.slice(0, 1000) ? rate : 0.05), changed: true }
}

function compactNumbers(items: string[]) {
  return Object.entries(countItems(items)).map(([v, n]) => `${v}*${n}`).join('；')
}

function statusColor(status?: string) {
  if (status === 'success') return 'green'
  if (status === 'complete_with_empty') return 'blue'
  if (status === 'partial') return 'orange'
  if (status === 'failed') return 'red'
  if (status === 'running') return 'processing'
  return 'default'
}

function statusText(status?: string) {
  if (status === 'success') return '成功'
  if (status === 'complete_with_empty') return '有空段'
  if (status === 'partial') return '部分'
  if (status === 'failed') return '失败'
  if (status === 'running') return '进行中'
  if (status === 'missing') return '未转写'
  return status || '未知'
}

function matchColor(status: MatchStatus) {
  if (status === 'match') return 'green'
  if (status === 'mismatch') return 'red'
  return 'default'
}

function matchText(status: MatchStatus) {
  if (status === 'match') return '✅'
  if (status === 'mismatch') return '❌'
  return '-'
}

function isStructuredField(key: string) {
  return fieldColumns.some((field) => field.key === key)
}

function formatPercent(value?: number | null) {
  if (value == null || !Number.isFinite(Number(value))) return '-'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function openAsrDetail(row: any) {
  asrDetailRow.value = row
  asrDetailOpen.value = true
}

function openStructuredDetail(row: any) {
  examDetailRow.value = row
  examDetailVisible.value = true
}

function openFieldDetail(row: any, fieldKey: string) {
  fieldDetailRow.value = row
  fieldDetailField.value = fieldKey
  prepareStructuredMarkForm(row, fieldKey)
  fieldDetailOpen.value = true
}

function getFieldLabel(fieldKey: string) {
  return fieldColumns.find((field) => field.key === fieldKey)?.label || fieldKey
}

function getStructuredFieldValue(row: any, fieldKey: string) {
  const structured = row?.llm?.structured_result || row?.llm?.structured || {}
  if (fieldKey === 'right_follicle') return { total: structured.right_follicle_total, follicles: structured.right_follicles }
  if (fieldKey === 'left_follicle') return { total: structured.left_follicle_total, follicles: structured.left_follicles }
  if (fieldKey === 'right_ovary') return { length: structured.right_ovary_length, width: structured.right_ovary_width }
  if (fieldKey === 'left_ovary') return { length: structured.left_ovary_length, width: structured.left_ovary_width }
  return structured[fieldKey]
}

function getGroundTruthFieldValue(row: any, fieldKey: string) {
  const result = row?.record?.result || {}
  if (fieldKey === 'right_follicle') return { total: result.right_follicle_total, follicles: result.right_follicles }
  if (fieldKey === 'left_follicle') return { total: result.left_follicle_total, follicles: result.left_follicles }
  if (fieldKey === 'right_ovary') return { length: result.right_ovary_length, width: result.right_ovary_width }
  if (fieldKey === 'left_ovary') return { length: result.left_ovary_length, width: result.left_ovary_width }
  return result[fieldKey]
}

function formatFieldValue(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

function exportExcel() {
  if (!asrCompareRows.value.length) {
    message.warning('当前没有可导出的优化评估数据')
    return
  }

  const aName = slotDisplayName(getSlot('A'))
  const bName = slotDisplayName(getSlot('B'))
  const cName = slotDisplayName(getSlot('C'))
  const asrHeaders = ['病历号', '日期', `${aName}转写内容`, `${bName}转写内容`, `${cName}转写内容`]
  const asrRows = asrCompareRows.value.map((row) => [
    row.record_id,
    row.date,
    formatAsrExportCell(row.a_status, row.a_text, row.a_error, row.same_config),
    formatAsrExportCell(row.b_status, row.b_text, row.b_error, row.same_config),
    formatAsrExportCell(row.c_status, row.c_text, row.c_error, row.same_config),
  ])

  const structuredHeaders = [
    '病历号',
    '日期',
    '录音',
    '真实结果',
    'ASR方案',
    'LLM方案',
    '准确率',
    ...fieldColumns.map((field) => `${field.label}-状态`),
    ...fieldColumns.map((field) => `${field.label}-问题`),
  ]
  const structuredExportRows = structuredRows.value.map((row) => [
    row.record_id,
    row.date,
    row.has_audio ? `有(${row.seg_count}段)` : '无',
    row.has_result ? '有' : '无',
    row.asr_slot,
    row.llm_name,
    formatPercent(row.accuracy),
    ...fieldColumns.map((field) => matchText(row.field_status[field.key])),
    ...fieldColumns.map((field) => row.field_notes[field.key] || ''),
  ])

  const html = `
    <html>
      <head>
        <meta charset="UTF-8" />
        <style>
          table { border-collapse: collapse; margin-bottom: 24px; }
          th, td { border: 1px solid #999; padding: 6px 8px; vertical-align: top; mso-number-format:'\\@'; }
          th { background: #f2f2f2; font-weight: bold; }
          .title { font-size: 18px; font-weight: bold; margin: 12px 0; }
          .text { white-space: pre-wrap; }
        </style>
      </head>
      <body>
        <div class="title">ASR 转写对比</div>
        ${excelTable(asrHeaders, asrRows)}
        <div class="title">结构化结果</div>
        ${excelTable(structuredHeaders, structuredExportRows)}
      </body>
    </html>
  `

  const blob = new Blob([html], { type: 'application/vnd.ms-excel;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const datePart = selectedDate.value === 'all' ? 'all' : selectedDate.value
  link.href = url
  link.download = `优化评估_${datePart}_${new Date().toISOString().slice(0, 10)}.xls`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  message.success('已导出优化评估 Excel')
}

async function exportFullExcel() {
  if (!activeSlot.value.model_id) {
    message.warning('请先选择当前 ASR 方案')
    return
  }
  const configHash = slotConfigHash(activeSlot.value)
  const dates = selectedDate.value === 'all' ? [] : [selectedDate.value]
  fullExporting.value = true
  try {
    const blob = await asrOptimizationApi.exportFull({ config_hash: configHash, dates }) as Blob
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const datePart = selectedDate.value === 'all' ? 'all' : selectedDate.value
    link.href = url
    link.download = `ASR优化评估完整数据_${configHash.slice(0, 10)}_${datePart}_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    message.success('已导出当前指纹完整数据')
  } finally {
    fullExporting.value = false
  }
}

function excelTable(headers: string[], rows: any[][]) {
  const head = `<tr>${headers.map((header) => `<th>${htmlEscape(header)}</th>`).join('')}</tr>`
  const body = rows.map((row) => `<tr>${row.map((cell) => `<td class="text">${htmlEscape(formatExcelCell(cell))}</td>`).join('')}</tr>`).join('')
  return `<table>${head}${body}</table>`
}

function formatExcelCell(value: any) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function formatAsrExportCell(status: string, text: string, error: string, sameConfig: boolean) {
  const parts = [`状态：${statusText(status)}`]
  if (sameConfig) parts.push('提示：方案同配置')
  if (error) parts.push(`错误：${error}`)
  parts.push(text || '暂无文本')
  return parts.join('\n')
}

function htmlEscape(value: any) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
</script>

<style scoped>
.asr-optimize-page { width: 100%; min-width: 0; }
.page-card { width: 100%; }
.sub-title, .muted { color: #888; font-size: 12px; font-weight: 400; }
.label { color: #666; }
.filter-bar, .structured-toolbar, .field-stats-row, .prompt-run-switch, .attribution-filters {
  margin-bottom: 10px;
  padding: 10px 12px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
}
.asr-plan-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 10px;
}
.asr-plan-card { cursor: pointer; border: 2px solid transparent; }
.asr-plan-card.active { border-color: #1677ff; box-shadow: 0 0 0 2px rgba(22,119,255,0.08); }
.asr-plan-card.no-model {
  opacity: 0.55;
  background: #f5f5f5;
  filter: grayscale(0.3);
}
.asr-plan-card.no-model :deep(.ant-card-head) {
  background: #fafafa;
}
.asr-plan-card.no-model :deep(.ant-card-body) {
  color: #999;
}
.asr-plan-card :deep(.ant-card-head) {
  min-height: 36px;
  padding: 0 10px;
}
.asr-plan-card :deep(.ant-card-head-title) {
  padding: 7px 0;
}
.asr-plan-card :deep(.ant-card-extra) {
  padding: 7px 0;
}
.asr-plan-card :deep(.ant-card-body) {
  padding: 6px 8px 8px;
}
.slot-compact {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}
.slot-meta {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(100px, 1fr));
  gap: 3px 10px;
  color: #333;
  font-size: 11px;
  line-height: 1.5;
}
.slot-meta span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.slot-actions {
  flex: 0 0 auto;
}
.switch-row { margin-bottom: 12px; }
.form-tip { margin-top: 6px; color: #888; font-size: 12px; }
.provider-card {
  margin-bottom: 12px;
}
.provider-card :deep(.ant-card-body) {
  padding: 12px;
}
.history-filter {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  padding: 10px 12px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
}
.plan-select-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(260px, 1fr));
  gap: 10px;
  max-height: 330px;
  overflow: auto;
  padding-right: 4px;
}
.plan-select-card {
  cursor: pointer;
  border: 1px solid #f0f0f0;
}
.plan-select-card.active {
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22,119,255,0.08);
}
.plan-card-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(110px, 1fr));
  gap: 4px 10px;
  color: #333;
  font-size: 12px;
  line-height: 1.6;
}
.plan-card-actions {
  margin-top: 10px;
  text-align: right;
}
.plan-preview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(240px, 1fr));
  gap: 12px;
}
.plan-preview-text {
  min-height: 92px;
  max-height: 220px;
  overflow: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: #333;
  font-size: 12px;
  line-height: 1.7;
}
.number-diff { color: #d46b08; font-size: 12px; line-height: 1.6; }
.asr-log-panel {
  margin-bottom: 10px;
  padding: 10px 12px;
  background: #fcfcff;
  border: 1px solid #e6f0ff;
  border-radius: 8px;
}
.asr-log-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 6px;
}
.asr-log-list {
  max-height: 180px;
  overflow: auto;
  margin-top: 8px;
  padding: 8px;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.7;
}
.asr-log-line { color: #555; }
.asr-log-line.success { color: #389e0d; }
.asr-log-line.error { color: #cf1322; }
.asr-log-line.warning { color: #d46b08; }
.asr-log-time {
  display: inline-block;
  min-width: 78px;
  color: #999;
}
.asr-text-cell {
  min-height: 160px;
  max-height: 360px;
  overflow: auto;
  word-break: break-word;
  line-height: 1.7;
  font-size: 12px;
}
.asr-text-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin-bottom: 6px;
}
.asr-integrity-note {
  margin: 0 0 6px;
  color: #d46b08;
  font-size: 12px;
  line-height: 1.4;
}
.asr-text-content {
  white-space: pre-wrap;
}
.asr-diff-segment {
  color: #cf1322;
  background: #fff1f0;
  border-radius: 2px;
  padding: 0 1px;
}
.asr-error {
  color: #cf1322;
}
.chart-panel {
  margin-bottom: 10px;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
}
.chart-toolbar {
  margin-bottom: 10px;
}
.bar-chart {
  margin-bottom: 12px;
  padding: 8px 10px;
  background: #fafafa;
  border-radius: 8px;
}
.bar-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 8px;
  color: #666;
  font-size: 12px;
}
.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 4px;
  border-radius: 50%;
}
.legend-dot.overall,
.bar-fill.overall {
  background: #1677ff;
}
.legend-dot.follicle,
.bar-fill.follicle {
  background: #52c41a;
}
.bar-row {
  display: grid;
  grid-template-columns: minmax(160px, 260px) minmax(120px, 1fr) 56px minmax(120px, 1fr) 56px 66px;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  font-size: 12px;
}
.bar-name {
  overflow: hidden;
  color: #333;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bar-track {
  height: 10px;
  overflow: hidden;
  background: #f0f0f0;
  border-radius: 999px;
}
.bar-fill {
  height: 100%;
  border-radius: 999px;
}
.bar-value {
  color: #333;
  font-variant-numeric: tabular-nums;
}
.bar-count {
  color: #888;
}
.heatmap-wrap {
  overflow-x: auto;
}
.heatmap-title {
  margin-bottom: 6px;
  color: #666;
  font-size: 12px;
  font-weight: 600;
}
.heatmap-grid {
  display: grid;
  min-width: 760px;
  border-top: 1px solid #f0f0f0;
  border-left: 1px solid #f0f0f0;
}
.heatmap-head,
.heatmap-field,
.heatmap-cell {
  min-height: 36px;
  padding: 6px 8px;
  border-right: 1px solid #f0f0f0;
  border-bottom: 1px solid #f0f0f0;
  font-size: 12px;
}
.heatmap-head {
  display: flex;
  align-items: center;
  color: #333;
  font-weight: 700;
  background: #fafafa;
}
.group-head {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.heatmap-field {
  display: flex;
  align-items: center;
  color: #333;
  font-weight: 600;
  background: #fff;
}
.heatmap-cell {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 1px;
  color: #333;
  font-variant-numeric: tabular-nums;
}
.heatmap-cell small {
  color: #666;
}
.match-tag { min-width: 32px; text-align: center; }
.attribution-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(160px, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}
.attribution-stat-card :deep(.ant-card-body) {
  padding: 10px 12px;
}
.stat-label {
  color: #666;
  font-size: 12px;
}
.stat-value {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.4;
}
.stat-value.success { color: #389e0d; }
.stat-value.danger { color: #cf1322; }
.stat-value.warning { color: #d46b08; }
.stat-sub {
  color: #888;
  font-size: 12px;
}
.attribution-reason {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}
.detail-text {
  min-height: 220px;
  max-height: 520px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.8;
  padding: 12px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
}
.json-box {
  max-height: 420px;
  overflow: auto;
  padding: 12px;
  background: #111827;
  color: #e5e7eb;
  border-radius: 8px;
}
.detail-section-card {
  margin-bottom: 14px;
}
.detail-section-card :deep(.ant-card-body) {
  padding: 12px;
}
.detail-warning {
  margin-bottom: 10px;
  padding: 8px 10px;
  color: #ad6800;
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 6px;
  line-height: 1.6;
}
.text-box {
  padding: 10px 12px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.75;
}
.detail-transcript {
  min-height: 180px;
  max-height: 420px;
  overflow: auto;
}
.compare-value-cell {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}
.compare-value-cell.mismatch {
  color: #cf1322;
  font-weight: 500;
}
.field-diff-summary {
  min-height: 72px;
  padding: 12px;
  border-radius: 8px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  background: #fafafa;
  border: 1px solid #f0f0f0;
}
.field-diff-summary.green {
  color: #237804;
  background: #f6ffed;
  border-color: #b7eb8f;
}
.field-diff-summary.red {
  color: #cf1322;
  background: #fff1f0;
  border-color: #ffa39e;
}
.field-diff-summary.orange {
  color: #ad6800;
  background: #fff7e6;
  border-color: #ffd591;
}
.field-diff-summary.default {
  color: #666;
}
.field-cell {
  cursor: pointer;
  min-width: 82px;
}
.field-cell:hover .match-tag {
  box-shadow: 0 0 0 2px rgba(22,119,255,0.12);
}
.field-note {
  margin-top: 4px;
  color: #d46b08;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
}
.history-toolbar {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
}
.history-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}
.history-patient-panel {
  position: sticky;
  top: 10px;
  max-height: calc(100vh - 150px);
  overflow: hidden;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  background: #fff;
}
.history-patient-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
}
.history-patient-list {
  max-height: calc(100vh - 205px);
  overflow: auto;
  padding: 8px;
}
.history-patient-item {
  padding: 9px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.history-patient-item:hover {
  background: #f5f8ff;
}
.history-patient-item.active {
  background: #e6f4ff;
  border-color: #91caff;
}
.history-patient-main {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.history-record-id {
  font-weight: 700;
  color: #222;
}
.history-patient-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-bottom: 5px;
}
.history-patient-tags :deep(.ant-tag) {
  margin-inline-end: 0;
  font-size: 11px;
}
.history-patient-models {
  color: #777;
  font-size: 12px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-content-panel {
  min-width: 0;
}
.history-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(360px, 1fr));
  gap: 12px;
}
.history-asr-card {
  cursor: pointer;
  border-color: #f0f0f0;
}
.history-asr-card.selected {
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.12);
}
.history-asr-card :deep(.ant-card-head) {
  min-height: 42px;
}
.history-asr-card :deep(.ant-card-body) {
  padding: 10px 12px;
}
.history-asr-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(120px, 1fr));
  gap: 6px 10px;
  margin-bottom: 8px;
  color: #555;
  font-size: 12px;
}
.history-asr-text {
  min-height: 120px;
  max-height: 320px;
  overflow: auto;
  padding: 10px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.75;
  font-size: 12px;
}
.history-error {
  margin-top: 8px;
  white-space: pre-wrap;
}
.history-compare-panel {
  margin-top: 14px;
}
.history-compare-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.history-compare-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(360px, 1fr));
  gap: 12px;
}
.history-compare-text {
  max-height: 460px;
  overflow: auto;
  padding: 10px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  line-height: 1.75;
  word-break: break-word;
}
.history-compare-title {
  margin-bottom: 8px;
  font-weight: 600;
}
.reference-asr-panel {
  margin-bottom: 12px;
  border-color: #efdbff;
  background: #fcfaff;
}
.reference-asr-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.reference-asr-text,
.reference-annotation-preview {
  max-height: 260px;
  overflow: auto;
  padding: 10px;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.8;
  font-size: 12px;
}
.reference-asr-note {
  margin-top: 8px;
  color: #666;
  font-size: 12px;
}
.reference-annotation-toolbar {
  margin-bottom: 8px;
  padding: 8px 10px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
}
.reference-preview-title {
  margin: 10px 0 6px;
  color: #666;
  font-size: 12px;
  font-weight: 600;
}
.reference-mark {
  padding: 0 2px;
  border-radius: 2px;
}
.reference-mark-red {
  color: #cf1322;
  background: #fff1f0;
}
.reference-mark-orange {
  color: #d46b08;
  background: #fff7e6;
}
.reference-mark-green {
  color: #389e0d;
  background: #f6ffed;
}
.reference-audio-card {
  margin-bottom: 12px;
  border-color: #d6e4ff;
  background: #fbfdff;
}
.reference-audio-card :deep(.ant-card-body) {
  padding: 12px;
}
@media (max-width: 1100px) {
  .asr-plan-grid { grid-template-columns: repeat(2, 1fr); }
  .attribution-stats { grid-template-columns: repeat(2, minmax(160px, 1fr)); }
  .plan-select-grid { grid-template-columns: 1fr; }
  .plan-preview-grid { grid-template-columns: 1fr; }
  .slot-compact { align-items: flex-start; flex-direction: column; }
  .slot-meta { grid-template-columns: repeat(2, minmax(100px, 1fr)); width: 100%; }
  .history-card-grid { grid-template-columns: 1fr; }
  .history-compare-grid { grid-template-columns: 1fr; }
  .history-asr-meta { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
  .history-layout { grid-template-columns: 1fr; }
  .history-patient-panel { position: static; max-height: none; }
  .history-patient-list { max-height: 320px; }
}
@media (max-width: 768px) {
  .asr-plan-grid { grid-template-columns: 1fr; }
  .slot-meta { grid-template-columns: 1fr; }
}
</style>
