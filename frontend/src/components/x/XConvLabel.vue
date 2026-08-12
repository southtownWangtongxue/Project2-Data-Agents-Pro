<script setup lang="ts">
/**
 * XConvLabel.vue — 会话名渲染（支持内联重命名编辑）
 * 编辑状态隔离在本组件内部，避免父级 computed 重建导致 Input 失焦。
 */
import { ref, watch, nextTick } from 'vue'
import { Input } from 'ant-design-vue'

const props = defineProps<{
  value: string
  editing: boolean
}>()

const emit = defineEmits<{
  (e: 'rename', title: string): void
  (e: 'cancel'): void
}>()

const title = ref(props.value)
const inputRef = ref<{ focus: () => void } | null>(null)

watch(
  () => props.editing,
  (v) => {
    if (v) {
      title.value = props.value
      nextTick(() => inputRef.value?.focus())
    }
  },
)

function commitRename() {
  emit('rename', title.value.trim())
}

function onInput(e: Event) {
  title.value = (e.target as HTMLInputElement).value
}
</script>

<template>
  <Input
    v-if="editing"
    ref="inputRef"
    :value="title"
    size="small"
    @input="onInput"
    @press-enter="commitRename"
    @blur="commitRename"
  />
  <span v-else class="x-conv-label">{{ value }}</span>
</template>

<style scoped>
.x-conv-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
}
</style>
