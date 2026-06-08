<template>
  <div v-loading="loading">
    <el-page-header @back="$router.push('/')" style="margin-bottom: 20px">
      <template #content>
        <span>崩溃详情 - {{ crash?.id }}</span>
      </template>
    </el-page-header>

    <template v-if="crash">
      <!-- 基本信息 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <template #header><strong>基本信息</strong></template>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="游戏">{{ crash.game_name }}</el-descriptions-item>
          <el-descriptions-item label="引擎版本">{{ crash.engine_version }}</el-descriptions-item>
          <el-descriptions-item label="构建版本">{{ crash.build_version }}</el-descriptions-item>
          <el-descriptions-item label="平台">{{ crash.platform }}</el-descriptions-item>
          <el-descriptions-item label="崩溃类型">
            <el-tag size="small" type="danger">{{ crash.crash_type }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="statusType(crash.status)">{{ statusLabel(crash.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="错误信息" :span="3">
            <code>{{ crash.error_message }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="崩溃线程">{{ crash.crashed_thread }}</el-descriptions-item>
          <el-descriptions-item label="上传时间">{{ formatTime(crash.upload_time) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 符号匹配 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <template #header>
          <div style="display: flex; justify-content: space-between; align-items: center">
            <strong>符号匹配</strong>
            <el-button
              type="warning"
              size="small"
              :loading="resymbolicating"
              @click="handleResymbolicate"
            >
              重新符号化
            </el-button>
          </div>
        </template>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="当前符号包">
            <el-tag v-if="crash.symbol_package_id" size="small" type="success">{{ crash.symbol_package_id }}</el-tag>
            <el-tag v-else size="small" type="warning">未匹配（使用默认路径）</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="指定符号包">
            <el-select
              v-model="selectedSymbolId"
              placeholder="自动匹配"
              clearable
              size="small"
              style="width: 260px"
            >
              <el-option
                v-for="s in symbolOptions"
                :key="s.id"
                :label="`${s.game_name || s.id} / ${s.build_version || '-'} / ${s.platform} (${s.id})`"
                :value="s.id"
              />
            </el-select>
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="crash.module_guids && crash.module_guids.length > 0" style="margin-top: 12px">
          <el-collapse>
            <el-collapse-item>
              <template #title>
                <span style="font-weight: bold; font-size: 13px">
                  DMP 模块 GUID（{{ crash.module_guids.length }} 个模块）
                </span>
                <el-tag v-if="crash.symbol_package_id" size="small" type="success"
                        style="margin-left: 8px">已匹配</el-tag>
                <el-tag v-else size="small" type="warning"
                        style="margin-left: 8px">未匹配</el-tag>
              </template>
              <el-table :data="crash.module_guids" size="small" stripe max-height="300">
                <el-table-column prop="module_name" label="模块" width="200" show-overflow-tooltip />
                <el-table-column prop="guid" label="PDB GUID" width="300">
                  <template #default="{ row }">
                    <code style="font-size: 11px">{{ row.guid }}</code>
                  </template>
                </el-table-column>
                <el-table-column prop="age" label="Age" width="60" />
                <el-table-column prop="pdb_filename" label="PDB 文件" show-overflow-tooltip />
              </el-table>
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-card>

      <!-- 环境信息 -->
      <el-card shadow="never" style="margin-bottom: 16px" v-if="envInfo">
        <template #header><strong>环境信息</strong></template>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="CPU">{{ envInfo.cpu }}</el-descriptions-item>
          <el-descriptions-item label="GPU">{{ envInfo.gpu }}</el-descriptions-item>
          <el-descriptions-item label="内存">{{ envInfo.ram }}</el-descriptions-item>
          <el-descriptions-item label="操作系统">{{ envInfo.os }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 调用栈 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <template #header><strong>调用栈</strong></template>
        <el-tabs v-model="stackTab">
          <el-tab-pane label="符号化调用栈" name="symbolicated" v-if="crash.symbolicated_callstack">
            <pre class="stack-trace">{{ crash.symbolicated_callstack }}</pre>
          </el-tab-pane>
          <el-tab-pane label="原始地址" name="raw">
            <pre class="stack-trace">{{ crash.raw_callstack || '无调用栈数据' }}</pre>
          </el-tab-pane>
        </el-tabs>
      </el-card>

      <!-- 日志 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <template #header>
          <div style="display: flex; justify-content: space-between; align-items: center">
            <strong>应用日志</strong>
            <el-switch v-model="showFullLog" active-text="完整日志" inactive-text="尾部200行" />
          </div>
        </template>
        <pre class="log-content">{{ showFullLog ? crash.log_content : crash.log_tail }}</pre>
      </el-card>

      <!-- AI 分析 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <template #header>
          <div style="display: flex; justify-content: space-between; align-items: center">
            <strong>AI 崩溃分析</strong>
            <el-button
              type="primary"
              :loading="analyzing"
              :disabled="analyzing"
              @click="runAnalysis"
            >
              {{ analyzing ? '分析中...' : '开始分析' }}
            </el-button>
          </div>
        </template>

        <!-- 实时日志面板 -->
        <div v-if="analyzing || agentLog" style="margin-bottom: 16px">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
            <strong style="font-size: 13px; color: #909399">Copilot 实时日志</strong>
            <el-button v-if="!analyzing && agentLog" link size="small" @click="agentLog = ''">清除</el-button>
          </div>
          <pre ref="logPanelRef" class="agent-log">{{ agentLog }}<span v-if="analyzing" class="cursor-blink">|</span></pre>
        </div>

        <div v-if="analyses.length === 0 && !analyzing && !agentLog">
          <el-empty description="暂无分析报告，点击「开始分析」触发 AI 分析" />
        </div>

        <div v-for="report in analyses" :key="report.id" style="margin-bottom: 20px">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="Agent">
              <el-tag size="small">{{ report.agent_type }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="分析时间">{{ formatTime(report.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="严重程度">
              <el-tag :type="severityType(report.severity)" size="small">{{ report.severity || '未知' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="信心度">
              <div style="display: flex; align-items: center; gap: 8px" v-if="report.confidence != null">
                <el-progress
                  :percentage="report.confidence"
                  :color="confidenceColor(report.confidence)"
                  :stroke-width="16"
                  style="flex: 1"
                />
              </div>
              <span v-else>未知</span>
            </el-descriptions-item>
            <el-descriptions-item label="根因分析" :span="2">
              <div style="white-space: pre-wrap">{{ report.root_cause }}</div>
            </el-descriptions-item>
            <el-descriptions-item label="修复建议" :span="2">
              <div style="white-space: pre-wrap">{{ report.fix_suggestion || '无' }}</div>
            </el-descriptions-item>
          </el-descriptions>

          <el-collapse style="margin-top: 8px">
            <el-collapse-item title="查看 AI 原始响应">
              <pre class="raw-response">{{ report.raw_response }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getCrash, triggerAnalysis, getCrashStatus, getAnalysisLog, getAnalyses } from '../api/crash'
import { resymbolicate, listSymbols } from '../api/symbol'

const route = useRoute()
const crashId = route.params.id
const crash = ref(null)
const analyses = ref([])
const loading = ref(false)
const analyzing = ref(false)
const stackTab = ref('symbolicated')
const showFullLog = ref(false)
const agentLog = ref('')
const logPanelRef = ref(null)
const resymbolicating = ref(false)
const selectedSymbolId = ref(null)
const symbolOptions = ref([])
let pollTimer = null
let logOffset = 0

const envInfo = computed(() => {
  if (!crash.value?.crash_context_json) return null
  try {
    const ctx = JSON.parse(crash.value.crash_context_json)
    return {
      cpu: ctx['Misc.CPUBrand'] || '未知',
      gpu: ctx['Misc.PrimaryGPUBrand'] || '未知',
      ram: ctx['MemoryStats.TotalPhysicalGB'] ? `${ctx['MemoryStats.TotalPhysicalGB']} GB` : '未知',
      os: ctx['Misc.OSVersionMajor'] || '未知',
    }
  } catch { return null }
})

async function fetchData() {
  loading.value = true
  try {
    const { data } = await getCrash(crashId)
    crash.value = data
    analyses.value = data.analyses || []
    if (!data.symbolicated_callstack) stackTab.value = 'raw'
    if (data.status === 'analyzing') {
      startPolling()
    }
    loadSymbolOptions()
  } finally {
    loading.value = false
  }
}

async function loadSymbolOptions() {
  try {
    const { data } = await listSymbols({})
    symbolOptions.value = (data.items || []).filter(s => s.status === 'ready')
  } catch {}
}

async function handleResymbolicate() {
  resymbolicating.value = true
  try {
    const { data } = await resymbolicate(crashId, selectedSymbolId.value || undefined)
    crash.value.symbolicated_callstack = data.symbolicated_callstack
    crash.value.symbol_package_id = data.symbol_package_id
    stackTab.value = 'symbolicated'
    ElMessage.success('重新符号化完成')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '符号化失败')
  } finally {
    resymbolicating.value = false
  }
}

function scrollLogToBottom() {
  nextTick(() => {
    if (logPanelRef.value) {
      logPanelRef.value.scrollTop = logPanelRef.value.scrollHeight
    }
  })
}

async function runAnalysis() {
  analyzing.value = true
  agentLog.value = ''
  logOffset = 0

  try {
    await triggerAnalysis(crashId)
    crash.value.status = 'analyzing'
    startPolling()
  } catch (e) {
    analyzing.value = false
    const msg = e.response?.data?.detail || e.message || '分析启动失败'
    ElMessage.error(msg)
  }
}

function startPolling() {
  stopPolling()
  analyzing.value = true
  pollTimer = setInterval(pollUpdate, 1500)
  pollUpdate()
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pollUpdate() {
  try {
    const [logRes, statusRes] = await Promise.all([
      getAnalysisLog(crashId, logOffset),
      getCrashStatus(crashId),
    ])

    if (logRes.data.content) {
      agentLog.value += logRes.data.content
      logOffset = logRes.data.offset
      scrollLogToBottom()
    }

    const status = statusRes.data.status
    if (status === 'analyzed' || status === 'failed') {
      stopPolling()
      analyzing.value = false
      crash.value.status = status

      if (status === 'analyzed') {
        const { data } = await getAnalyses(crashId)
        analyses.value = data
        ElMessage.success('分析完成')
      } else {
        ElMessage.error('分析失败')
      }
    }
  } catch {
    // ignore transient polling errors
  }
}

const STATUS_MAP = {
  uploaded: { label: '已上传', type: 'info' },
  parsing: { label: '解析中', type: '' },
  parsed: { label: '已解析', type: 'success' },
  analyzing: { label: '分析中', type: 'warning' },
  analyzed: { label: '已分析', type: 'primary' },
  failed: { label: '失败', type: 'danger' },
}
function statusType(s) { return STATUS_MAP[s]?.type ?? 'info' }
function statusLabel(s) { return STATUS_MAP[s]?.label ?? s }

function severityType(s) {
  const m = { Critical: 'danger', High: 'warning', Medium: '', Low: 'success' }
  return m[s] ?? 'info'
}

function confidenceColor(v) {
  if (v >= 80) return '#67c23a'
  if (v >= 50) return '#e6a23c'
  return '#f56c6c'
}

function formatTime(t) {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN')
}

onMounted(fetchData)
onUnmounted(stopPolling)
</script>

<style scoped>
.stack-trace, .log-content, .raw-response {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 4px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  overflow-x: auto;
  max-height: 500px;
  overflow-y: auto;
  white-space: pre;
  margin: 0;
}

.agent-log {
  background: #0d1117;
  color: #58a6ff;
  padding: 16px;
  border-radius: 4px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.4;
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  border: 1px solid #21262d;
}

.cursor-blink {
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}
</style>
