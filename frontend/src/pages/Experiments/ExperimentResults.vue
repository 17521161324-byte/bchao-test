<template>
  <div class="page-container">
    <div class="page-header">
      <h2>实验结果对比</h2>
      <router-link :to="`/experiments/${batchId}`">
        <a-button><ArrowLeftOutlined />返回详情</a-button>
      </router-link>
    </div>

    <!-- 筛选 -->
    <a-card size="small" style="margin-bottom: 16px">
      <a-space>
        <span>显示：</span>
        <a-radio-group v-model:value="filter" button-style="solid" size="small">
          <a-radio-button value="all">全部</a-radio-button>
          <a-radio-button value="with_result">有LLM结果</a-radio-button>
          <a-radio-button value="mismatch">有差异</a-radio-button>
        </a-radio-group>
      </a-space>
    </a-card>

    <!-- 对比表格 -->
    <a-card>
      <a-table
        :data-source="filteredTasks"
        :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }"
        size="small"
        row-key="id"
        :scroll="{ x: 1400 }"
      >
        <a-table-column title="病历号" data-index="record_id" :width="100" fixed="left" />
        <a-table-column title="日期" data-index="date" :width="100" />
        <a-table-column title="状态" :width="80">
          <template #default="{ record }">
            <a-tag :color="record.status === 'success' ? 'green' : record.status === 'failed' ? 'red' : 'default'">
              {{ record.status }}
            </a-tag>
          </template>
        </a-table-column>

        <!-- 右侧卵泡 -->
        <a-table-column title="右卵泡" :width="120">
          <template #default="{ record }">
            <div>金标: {{ record.gt_right ?? '-' }}</div>
            <div :style="{ color: record.gt_right !== record.llm_right ? '#ff4d4f' : '#52c41a' }">
              LLM: {{ record.llm_right ?? '-' }}
            </div>
          </template>
        </a-table-column>

        <!-- 左侧卵泡 -->
        <a-table-column title="左卵泡" :width="120">
          <template #default="{ record }">
            <div>金标: {{ record.gt_left ?? '-' }}</div>
            <div :style="{ color: record.gt_left !== record.llm_left ? '#ff4d4f' : '#52c41a' }">
              LLM: {{ record.llm_left ?? '-' }}
            </div>
          </template>
        </a-table-column>

        <!-- 内膜厚度 -->
        <a-table-column title="内膜厚度" :width="100">
          <template #default="{ record }">
            <div>金标: {{ record.gt_endo_thick ?? '-' }}</div>
            <div :style="{ color: record.gt_endo_thick !== record.llm_endo_thick ? '#ff4d4f' : '#52c41a' }">
              LLM: {{ record.llm_endo_thick ?? '-' }}
            </div>
          </template>
        </a-table-column>

        <!-- 内膜类型 -->
        <a-table-column title="内膜类型" :width="80">
          <template #default="{ record }">
            <div>金标: {{ record.gt_endo_type ?? '-' }}</div>
            <div :style="{ color: record.gt_endo_type !== record.llm_endo_type ? '#ff4d4f' : '#52c41a' }">
              LLM: {{ record.llm_endo_type ?? '-' }}
            </div>
          </template>
        </a-table-column>

        <!-- 右卵巢 -->
        <a-table-column title="右卵巢" :width="100">
          <template #default="{ record }">
            <div>金标: {{ record.gt_r_ovary }}</div>
            <div :style="{ color: record.gt_r_ovary !== record.llm_r_ovary ? '#ff4d4f' : '#52c41a' }">
              LLM: {{ record.llm_r_ovary }}
            </div>
          </template>
        </a-table-column>

        <!-- 左卵巢 -->
        <a-table-column title="左卵巢" :width="100">
          <template #default="{ record }">
            <div>金标: {{ record.gt_l_ovary }}</div>
            <div :style="{ color: record.gt_l_ovary !== record.llm_l_ovary ? '#ff4d4f' : '#52c41a' }">
              LLM: {{ record.llm_l_ovary }}
            </div>
          </template>
        </a-table-column>

        <a-table-column title="耗时" :width="80">
          <template #default="{ record }">{{ record.total_duration?.toFixed(1) || '-' }}s</template>
        </a-table-column>
      </a-table>
    </a-card>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import { experimentApi } from '@/api/experiment'
import { audioApi } from '@/api/client'

export default defineComponent({
  name: 'ExperimentResults',
  setup() {
    const route = useRoute()
    const batchId = computed(() => Number(route.params.id))
    const tasks = ref<any[]>([])
    const groundTruths = ref<Record<number, any>>({})
    const filter = ref('all')

    const comparisonData = computed(() => {
      return tasks.value.map((task: any) => {
        const gt = groundTruths.value[task.patient_id] || {}
        const llm = task.structured_result || {}

        return {
          id: task.id,
          record_id: task.record_id || task.patient_record_id,
          date: task.date || '',
          status: task.status,
          total_duration: task.total_duration,

          gt_right: gt.right_follicle_total,
          gt_left: gt.left_follicle_total,
          gt_endo_thick: gt.endometrium_thickness,
          gt_endo_type: gt.endometrium_type,
          gt_r_ovary: formatOvary(gt.right_ovary_length, gt.right_ovary_width),
          gt_l_ovary: formatOvary(gt.left_ovary_length, gt.left_ovary_width),

          llm_right: llm.right_follicle_total,
          llm_left: llm.left_follicle_total,
          llm_endo_thick: llm.endometrium_thickness,
          llm_endo_type: llm.endometrium_type,
          llm_r_ovary: formatOvary(llm.right_ovary_length, llm.right_ovary_width),
          llm_l_ovary: formatOvary(llm.left_ovary_length, llm.left_ovary_width),
        }
      })
    })

    function formatOvary(l: number | undefined, w: number | undefined): string {
      return l && w ? `${l}×${w}` : '-'
    }

    const filteredTasks = computed(() => {
      let data = comparisonData.value
      if (filter.value === 'with_result') {
        data = data.filter((d) => d.llm_right !== undefined)
      } else if (filter.value === 'mismatch') {
        data = data.filter((d) => {
          return (
            d.gt_right !== d.llm_right ||
            d.gt_left !== d.llm_left ||
            d.gt_endo_thick !== d.llm_endo_thick ||
            d.gt_endo_type !== d.llm_endo_type
          )
        })
      }
      return data
    })

    async function fetchData() {
      try {
        const tasksRes = await experimentApi.tasks(batchId.value)
        tasks.value = tasksRes.data

        const gtRes = await audioApi.getTree()
        const gtMap: Record<number, any> = {}

        function extractPatients(node: any) {
          if (node.record_id && node.result) {
            gtMap[node.id] = node.result
          }
          for (const child of node.children || []) {
            extractPatients(child)
          }
        }

        for (const folder of gtRes.data) {
          extractPatients(folder)
        }
        groundTruths.value = gtMap
      } catch (e) {
        console.error('Failed to fetch data:', e)
      }
    }

    onMounted(fetchData)

    return { batchId, filter, filteredTasks }
  },
})
</script>
