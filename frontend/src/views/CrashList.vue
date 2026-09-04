<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 20px">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
        <h2 style="margin: 0">崩溃列表</h2>
        <el-button type="primary" @click="uploadDialogVisible = true">上传崩溃 ZIP</el-button>
      </div>
      <div style="display: flex; gap: 12px; flex-wrap: wrap">
        <el-input
          v-model="searchText"
          placeholder="搜索 Crash ID / 错误信息 / 版本 / 线程 / 备注"
          clearable
          style="width: 320px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="filterGame"
          placeholder="游戏名称"
          clearable
          style="width: 160px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-select v-model="filterPlatform" placeholder="平台" clearable style="width: 120px" @change="handleSearch">
          <el-option label="Windows" value="Windows" />
          <el-option label="Linux" value="Linux" />
          <el-option label="Mac" value="Mac" />
        </el-select>
        <el-select v-model="filterStatus" placeholder="解析状态" clearable style="width: 130px" @change="handleSearch">
          <el-option v-for="(v, k) in STATUS_MAP" :key="k" :label="v.label" :value="k" />
        </el-select>
        <el-select v-model="filterResolution" placeholder="解决状态" clearable style="width: 130px" @change="handleSearch">
          <el-option label="未解决" value="unresolved" />
          <el-option label="已解决" value="resolved" />
        </el-select>
        <el-button @click="handleSearch">搜索</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table
        :data="crashes"
        v-loading="loading"
        stripe
        style="width: 100%"
        @row-click="goDetail"
        row-class-name="clickable-row"
      >
        <el-table-column prop="id" label="Crash ID" width="200" show-overflow-tooltip />
        <el-table-column prop="game_name" label="游戏" width="140" />
        <el-table-column prop="error_message" label="错误信息" show-overflow-tooltip />
        <el-table-column prop="crash_type" label="类型" width="80" />
        <el-table-column prop="crashed_thread" label="崩溃线程" width="160" />
        <el-table-column prop="platform" label="平台" width="80" />
        <el-table-column label="符号包" width="160">
          <template #default="{ row }">
            <el-tag v-if="row.symbol_package_id" size="small" type="success">{{ row.symbol_package_id }}</el-tag>
            <el-tag v-else size="small" type="info">未匹配</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="解析状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="解决状态" width="100">
          <template #default="{ row }">
            <el-tag :type="resolutionType(row.resolution_status)" size="small">{{ resolutionLabel(row.resolution_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="color: #606266">{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="170">
          <template #default="{ row }">{{ formatTime(row.upload_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              :type="row.resolution_status === 'resolved' ? 'warning' : 'success'"
              size="small"
              @click.stop="handleToggleResolution(row)"
            >
              {{ row.resolution_status === 'resolved' ? '标为未解决' : '标为已解决' }}
            </el-button>
            <el-button link type="danger" size="small" @click.stop="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div style="display: flex; justify-content: flex-end; margin-top: 16px">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchCrashes"
          @current-change="fetchCrashes"
        />
      </div>
    </el-card>

    <el-dialog v-model="uploadDialogVisible" title="上传崩溃 ZIP" width="520px" :close-on-click-modal="false">
      <el-upload
        ref="uploadRef"
        v-model:file-list="uploadFileList"
        :auto-upload="false"
        :limit="1"
        accept=".zip"
        :on-change="handleFileChange"
        :on-exceed="handleFileExceed"
      >
        <el-button>选择 ZIP 文件</el-button>
        <template #tip>
          <div style="color: #909399; font-size: 12px; margin-top: 8px">仅支持 .zip 文件，一次上传一个</div>
        </template>
      </el-upload>
      <el-input
        v-model="uploadRemark"
        type="textarea"
        :rows="3"
        maxlength="2000"
        show-word-limit
        placeholder="备注（可选，例如：复现步骤、测试环境、联系人）"
        style="margin-top: 12px"
      />
      <el-select v-model="uploadResolution" style="margin-top: 12px; width: 100%">
        <el-option label="未解决" value="unresolved" />
        <el-option label="已解决" value="resolved" />
      </el-select>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="handleConfirmUpload">确认上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listCrashes, uploadCrash, deleteCrash, updateCrash } from '../api/crash'
import { formatTime } from '../utils/datetime'

const router = useRouter()
const crashes = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchText = ref('')
const filterGame = ref('')
const filterPlatform = ref('')
const filterStatus = ref('')
const filterResolution = ref('')

const uploadDialogVisible = ref(false)
const uploadFileList = ref([])
const uploadRemark = ref('')
const uploadResolution = ref('unresolved')
const uploading = ref(false)
const uploadRef = ref(null)

function handleSearch() {
  page.value = 1
  fetchCrashes()
}

async function fetchCrashes() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (searchText.value) params.search = searchText.value
    if (filterGame.value) params.game_name = filterGame.value
    if (filterPlatform.value) params.platform = filterPlatform.value
    if (filterStatus.value) params.status = filterStatus.value
    if (filterResolution.value) params.resolution_status = filterResolution.value
    const { data } = await listCrashes(params)
    // 兼容旧接口（直接返回数组）与新分页接口（{ total, items }）
    if (Array.isArray(data)) {
      crashes.value = data
      total.value = data.length
    } else {
      crashes.value = data.items || []
      total.value = data.total || 0
    }
  } finally {
    loading.value = false
  }
}

function handleFileChange(file, fileList) {
  uploadFileList.value = fileList.slice(-1)
}

function handleFileExceed() {
  ElMessage.warning('一次只能上传一个文件，已替换为最新选择的文件')
  // element-plus 会自动阻止，这里手动保留最后一个
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  }
  uploadFileList.value = []
}

async function handleConfirmUpload() {
  const entry = uploadFileList.value[0]
  const rawFile = entry?.raw || entry
  if (!rawFile) {
    ElMessage.warning('请先选择 ZIP 文件')
    return
  }
  if (rawFile.name && !rawFile.name.endsWith('.zip')) {
    ElMessage.error('请上传 .zip 文件')
    return
  }
  try {
    uploading.value = true
    await uploadCrash(rawFile, {
      remark: uploadRemark.value?.trim() || undefined,
      resolution_status: uploadResolution.value,
    })
    ElMessage.success('上传并解析成功')
    uploadDialogVisible.value = false
    uploadFileList.value = []
    uploadRemark.value = ''
    uploadResolution.value = 'unresolved'
    if (uploadRef.value) uploadRef.value.clearFiles()
    page.value = 1
    await fetchCrashes()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function handleToggleResolution(row) {
  const next = row.resolution_status === 'resolved' ? 'unresolved' : 'resolved'
  try {
    const { data } = await updateCrash(row.id, { resolution_status: next })
    row.resolution_status = data.resolution_status
    ElMessage.success(next === 'resolved' ? '已标为已解决' : '已标为未解决')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '更新状态失败')
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm('确定删除该崩溃记录？', '确认', { type: 'warning' })
    await deleteCrash(row.id)
    ElMessage.success('已删除')
    await fetchCrashes()
  } catch {}
}

function goDetail(row) {
  router.push({ name: 'CrashDetail', params: { id: row.id } })
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

const RESOLUTION_MAP = {
  unresolved: { label: '未解决', type: 'warning' },
  resolved: { label: '已解决', type: 'success' },
}

function resolutionType(s) { return RESOLUTION_MAP[s]?.type ?? 'info' }
function resolutionLabel(s) { return RESOLUTION_MAP[s]?.label ?? (s || '未解决') }

onMounted(fetchCrashes)
</script>

<style scoped>
:deep(.clickable-row) { cursor: pointer; }
</style>
