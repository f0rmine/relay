<template>
  <img v-if="imageUrl" class="image" :src="imageUrl" :alt="attachment.original_filename" />
  <div v-else class="image placeholder">{{ t('chat.imageUnavailable') }}</div>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue';
import { apiBlob } from '@/api/client';
import { useI18n } from 'vue-i18n';
import type { Attachment } from '@/api/types';

const props = defineProps<{ attachment: Attachment }>();
const imageUrl = ref('');
let objectUrl = '';
const { t } = useI18n();

function clearObjectUrl() {
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = '';
  imageUrl.value = '';
}

watch(
  () => props.attachment.id,
  async (attachmentId) => {
    clearObjectUrl();
    if (attachmentId.startsWith('local-attachment-')) {
      imageUrl.value = props.attachment.public_url;
      return;
    }
    try {
      const blob = await apiBlob(`/attachments/${attachmentId}/download`);
      objectUrl = URL.createObjectURL(blob);
      imageUrl.value = objectUrl;
    } catch {
      clearObjectUrl();
    }
  },
  { immediate: true }
);

onUnmounted(clearObjectUrl);
</script>

<style scoped>
.image {
  max-width: min(260px, 70vw);
  border-radius: 8px;
  display: block;
  margin-top: 6px;
}
.placeholder {
  display: grid;
  place-items: center;
  width: min(260px, 70vw);
  min-height: 120px;
  color: var(--relay-muted);
  background: rgba(255, 255, 255, 0.06);
}
</style>
