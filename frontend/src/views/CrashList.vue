<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 20px">
      <div style="display: flex; justify-content: space-between; align-items: center">
        <h2 style="margin: 0">崩溃列表</h2>
        <el-upload
          :show-file-list="false"
          :before-upload="handleUpload"
          accept=".zip"
        >
          <el-button type="primary">上传崩溃 ZIP</el-button>
        </el-upload>
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
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="170">
          <template #default="{ row }">{{ formatTime(row.upload_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click.stop="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listCrashes, uploadCrash, deleteCrash } from '../api/crash'

const router = useRouter()
const crashes = ref([])
const loading = ref(false)

async function fetchCrashes() {
  loading.value = true
  try {
    const { data } = await listCrashes()
    crashes.value = data
  } finally {
    loading.value = false
  }
}

async function handleUpload(file) {
  try {
    loading.value = true
    await uploadCrash(file)
    ElMessage.success('上传并解析成功')
    await fetchCrashes()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally {
    loading.value = false
  }
  return false
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

function formatTime(t) {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN')
}

onMounted(fetchCrashes)
</script>

<style scoped>
:deep(.clickable-row) { cursor: pointer; }
</style>
