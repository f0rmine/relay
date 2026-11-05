<template>
  <a
    v-if="preview"
    class="link-preview"
    :href="preview.url || undefined"
    target="_blank"
    rel="noopener noreferrer"
    @click.stop
  >
    <img v-if="imageSrc" class="link-preview-image" :src="imageSrc" :alt="preview.title || ''" />
    <span class="link-preview-body">
      <span v-if="preview.title" class="link-preview-title">{{ preview.title }}</span>
      <span v-if="preview.description" class="link-preview-desc">{{ preview.description }}</span>
      <span v-if="preview.url" class="link-preview-url">{{ preview.url }}</span>
    </span>
  </a>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue';
import { apiBlob } from '@/api/client';
import type { LinkPreview } from '@/api/types';

const props = defineProps<{ preview: LinkPreview | null | undefined }>();
const imageSrc = ref('');
let objectUrl = '';
let loadSequence = 0;

function clearObjectUrl() {
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = '';
}

watch(
  () => props.preview?.image_attachment_id ?? props.preview?.image_url ?? '',
  async () => {
    const sequence = ++loadSequence;
    clearObjectUrl();
    imageSrc.value = '';
    const attachmentId = props.preview?.image_attachment_id;
    if (attachmentId) {
      try {
        const blob = await apiBlob(`/attachments/${attachmentId}/download`);
        if (sequence !== loadSequence) return;
        objectUrl = URL.createObjectURL(blob);
        imageSrc.value = objectUrl;
        return;
      } catch {
        if (sequence !== loadSequence) return;
      }
    }
    if (props.preview?.image_url) imageSrc.value = props.preview.image_url;
  },
  { immediate: true }
);

onUnmounted(() => {
  loadSequence += 1;
  clearObjectUrl();
});
</script>

<style scoped>
.link-preview {
  display: flex;
  flex-direction: column;
  margin-top: 6px;
  border: 1px solid var(--relay-border);
  border-radius: 10px;
  background: var(--relay-panel);
  overflow: hidden;
  text-decoration: none;
  color: var(--ion-text-color);
  max-width: min(280px, 72vw);
}
.link-preview-image {
  display: block;
  width: 100%;
  max-height: 160px;
  object-fit: cover;
}
.link-preview-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
}
.link-preview-title {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.link-preview-desc {
  font-size: 12px;
  color: var(--relay-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.link-preview-url {
  font-size: 11px;
  color: var(--ion-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
