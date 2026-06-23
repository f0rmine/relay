<template>
  <div v-if="visible" class="typing">{{ t('chat.typing') }}</div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

defineProps<{ visible: boolean }>();
const { t } = useI18n();
</script>

<style scoped>
.typing {
  padding: 2px 14px 8px;
  color: var(--relay-muted);
  font-size: 13px;
}
</style>
