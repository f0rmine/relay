<template>
  <div class="state">{{ message }}</div>
</template>

<script setup lang="ts">
defineProps<{ message: string }>();
</script>

<style scoped>
.state {
  margin: 16px;
  padding: 12px;
  border: 1px solid #8f3f3f;
  border-radius: 8px;
  color: #ffb4b4;
  background: rgba(143, 63, 63, 0.15);
}
</style>
