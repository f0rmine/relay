<template>
  <div class="state" role="status" aria-live="polite">{{ message }}</div>
</template>

<script setup lang="ts">
defineProps<{ message: string }>();
</script>

<style scoped>
.state {
  margin: 16px;
  padding: 12px;
  border: 1px solid #34734d;
  border-radius: 8px;
  color: #b9f6ca;
  background: rgba(52, 115, 77, 0.18);
}
</style>
