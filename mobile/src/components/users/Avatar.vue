<template>
  <img v-if="imageUrl && !imageFailed" class="avatar" :src="imageUrl" :alt="name" @error="imageFailed = true" />
  <div v-else class="avatar placeholder" :style="{ background: placeholderColor }" aria-hidden="true">
    {{ initials }}
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { absoluteUrl } from '@/config/env';

const props = defineProps<{ url?: string | null; name: string; size?: number }>();

const imageFailed = ref(false);
const imageUrl = computed(() => absoluteUrl(props.url));
watch(imageUrl, () => {
  imageFailed.value = false;
});
const initials = computed(() => {
  const words = props.name.trim().split(/\s+/).filter(Boolean);
  const first = words[0]?.[0] || '?';
  const second = words.length > 1 ? words[1]?.[0] : words[0]?.[1];
  return `${first}${second || ''}`.toUpperCase();
});
const placeholderColor = computed(() => {
  let hash = 0;
  for (const char of props.name) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  return `hsl(${hash}, 48%, 34%)`;
});
</script>

<style scoped>
.avatar {
  width: v-bind('`${props.size || 42}px`');
  height: v-bind('`${props.size || 42}px`');
  border-radius: 50%;
  object-fit: cover;
  background: #223246;
}
.placeholder {
  display: grid;
  place-items: center;
  color: #f4f8ff;
  font-weight: 700;
  font-size: calc(v-bind('`${props.size || 42}px`') * 0.38);
  letter-spacing: 0;
  user-select: none;
}
</style>
