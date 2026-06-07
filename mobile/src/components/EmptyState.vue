<template>
  <div class="state">
    <strong>{{ title }}</strong>
    <p v-if="text">{{ text }}</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; text?: string }>();
</script>

<style scoped>
.state {
  padding: 40px 24px;
  text-align: center;
  color: var(--relay-muted);
}
.state strong {
  display: block;
  color: var(--ion-text-color);
  margin-bottom: 8px;
}
</style>
