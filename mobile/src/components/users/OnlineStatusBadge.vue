<template>
  <span class="status" :class="{ online }">{{ online ? t('presence.online') : label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps<{ online?: boolean; lastSeen?: string | null }>();
const { d, t } = useI18n();
const label = computed(() => props.lastSeen
  ? t('presence.lastSeen', { date: d(new Date(props.lastSeen), 'dateTime') })
  : t('presence.offline'));
</script>

<style scoped>
.status {
  color: var(--relay-muted);
  font-size: 12px;
}
.status.online {
  color: #5ecb88;
}
</style>
