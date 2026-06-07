<template>
  <span class="status" :class="{ online }">{{ online ? 'online' : label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{ online?: boolean; lastSeen?: string | null }>();
const label = computed(() => props.lastSeen ? `last seen ${new Date(props.lastSeen).toLocaleString()}` : 'offline');
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
