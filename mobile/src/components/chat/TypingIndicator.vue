<template>
  <div v-if="visible" class="typing">typing...</div>
</template>

<script setup lang="ts">
defineProps<{ visible: boolean }>();
</script>

<style scoped>
.typing {
  padding: 2px 14px 8px;
  color: var(--relay-muted);
  font-size: 13px;
}
</style>
