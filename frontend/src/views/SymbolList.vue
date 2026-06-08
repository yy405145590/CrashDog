<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 20px">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
        <h2 style="margin: 0">符号文件管理</h2>
        <el-button type="primary" @click="uploadVisible = true">上传符号包</el-button>
      </div>
      <div style="display: flex; gap: 12px">
        <el-select v-model="filterGame" placeholder="游戏名称" clearable style="width: 160px" @change="fetchSymbols">
          <el-option v-for="g in gameOptions" :key="g" :label="g" :value="g" />
        </el-select>
        <el-select v-model="filterPlatform" placeholder="平台" clearable style="width: 120px" @change="fetchSymbols">
          <el-option label="Windows" value="Windows" />
          <el-option label="Linux" value="Linux" />
          <el-option label="Mac" value="Mac" />
        </el-select>
        <el-input
          v-model="searchText"
          placeholder="搜索版本号或SVN修订号"
          clearable
          style="width: 240px"
          @keyup.enter="fetchSymbols"
          @clear="fetchSymbols"
        />
        <el-button @click="fetchSymbols">搜索</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table :data="symbols" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="id" label="符号包ID" width="160" show-overflow-tooltip />
        <el-table-column prop="game_name" label="游戏名称" width="140" />
        <el-table-column prop="build_version" label="版本号" width="140" />
        <el-table-column prop="svn_revision" label="SVN" width="100" />
        <el-table-column prop="platform" label="平台" width="90" />
        <el-table-column label="大小" width="110">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关联崩溃" width="90" align="center">
          <template #default="{ row }">{{ row.linked_crash_count }}</template>
        </el-table-column>
        <el-table-column label="GUID数" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.guid_count || 0 }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="170">
          <template #default="{ row }">{{ formatTime(row.upload_time) }}</template>
        </el-table-column>
        <el-table-column prop="description" label="备注" show-overflow-tooltip />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 上传对话框 -->
    <el-dialog v-model="uploadVisible" title="上传符号包" width="520px" :close-on-click-modal="false">
      <el-alert
        type="info"
        :closable="false"
        style="margin-bottom: 16px"
        description="上传后将自动提取 PDB GUID，崩溃日志通过 GUID 自动匹配符号包。游戏名称和版本号仅用于显示。"
      />
      <el-form :model="uploadForm" label-width="100px">
        <el-form-item label="游戏名称">
          <el-input v-model="uploadForm.game_name" placeholder="可选，用于显示" />
        </el-form-item>
        <el-form-item label="版本号">
          <el-input v-model="uploadForm.build_version" placeholder="可选，用于显示" />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="uploadForm.platform" style="width: 100%">
            <el-option label="Windows" value="Windows" />
            <el-option label="Linux" value="Linux" />
            <el-option label="Mac" value="Mac" />
          </el-select>
        </el-form-item>
        <el-form-item label="SVN修订号">
          <el-input v-model="uploadForm.svn_revision" placeholder="可选" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="uploadForm.description" placeholder="可选" />
        </el-form-item>
        <el-form-item label="符号文件">
          <el-upload
            ref="uploadRef"
            drag
            :auto-upload="false"
            :limit="1"
            accept=".zip"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
          >
            <div style="padding: 20px 0">
              <div style="font-size: 40px; color: #c0c4cc">+</div>
              <div style="color: #909399; margin-top: 8px">拖拽或点击上传 ZIP 文件</div>
            </div>
          </el-upload>
          <el-progress
            v-if="uploading"
            :percentage="uploadProgress"
            :stroke-width="10"
            style="margin-top: 8px"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetUpload">取消</el-button>
        <el-button type="primary" :loading="uploading" :disabled="!canUpload" @click="doUpload">上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listSymbols, uploadSymbol, deleteSymbol } from '../api/symbol'

const symbols = ref([])
const loading = ref(false)
const filterGame = ref('')
const filterPlatform = ref('')
const searchText = ref('')
const gameOptions = ref([])

const uploadVisible = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadFile = ref(null)
const uploadRef = ref(null)
const uploadForm = ref({
  game_name: '',
  build_version: '',
  platform: 'Windows',
  svn_revision: '',
  description: '',
})

const canUpload = computed(() => {
  return !!uploadFile.value
})

async function fetchSymbols() {
  loading.value = true
  try {
    const params = {}
    if (filterGame.value) params.game_name = filterGame.value
    if (filterPlatform.value) params.platform = filterPlatform.value
    if (searchText.value) params.search = searchText.value
    const { data } = await listSymbols(params)
    symbols.value = data.items || []
    const games = new Set(symbols.value.map(s => s.game_name))
    if (filterGame.value) games.add(filterGame.value)
    gameOptions.value = [...games]
  } finally {
    loading.value = false
  }
}

function handleFileChange(file) {
  uploadFile.value = file.raw
}

function handleFileRemove() {
  uploadFile.value = null
}

function resetUpload() {
  uploadVisible.value = false
  uploading.value = false
  uploadProgress.value = 0
  uploadFile.value = null
  uploadForm.value = { game_name: '', build_version: '', platform: 'Windows', svn_revision: '', description: '' }
  if (uploadRef.value) uploadRef.value.clearFiles()
}

async function doUpload() {
  uploading.value = true
  uploadProgress.value = 0
  try {
    await uploadSymbol(uploadFile.value, uploadForm.value, (e) => {
      if (e.total) uploadProgress.value = Math.round(e.loaded / e.total * 100)
    })
    ElMessage.success('符号包上传成功')
    resetUpload()
    await fetchSymbols()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm('确定删除该符号包？删除后关联的崩溃将取消关联。', '确认', { type: 'warning' })
    await deleteSymbol(row.id)
    ElMessage.success('已删除')
    await fetchSymbols()
  } catch {}
}

const STATUS_MAP = {
  uploading: { label: '上传中', type: 'warning' },
  ready: { label: '就绪', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

function statusType(s) { return STATUS_MAP[s]?.type ?? 'info' }
function statusLabel(s) { return STATUS_MAP[s]?.label ?? s }

function formatSize(bytes) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
}

function formatTime(t) {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN')
}

onMounted(fetchSymbols)
</script>
