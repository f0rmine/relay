<template>
  <img v-if="imageUrl" class="image" :src="imageUrl" :alt="attachment.original_filename" @click.stop="emit('open', attachment.id)" />
  <div v-else class="image placeholder">{{ t('chat.imageUnavailable') }}</div>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue';
import { apiBlob } from '@/api/client';
import { useI18n } from 'vue-i18n';
import type { Attachment } from '@/api/types';

const props = defineProps<{ attachment: Attachment }>();
const emit = defineEmits<{ open: [attachmentId: string] }>();
const imageUrl = ref('');
let objectUrl = '';
let loadSequence = 0;
const { t } = useI18n();

function clearObjectUrl() {
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = '';
  imageUrl.value = '';
}

watch(
  () => props.attachment.id,
  async (attachmentId) => {
    const sequence = ++loadSequence;
    clearObjectUrl();
    if (attachmentId.startsWith('local-attachment-')) {
      imageUrl.value = props.attachment.public_url;
      return;
    }
    try {
      const blob = await apiBlob(`/attachments/${attachmentId}/download?variant=thumb`);
      if (sequence !== loadSequence) return;
      objectUrl = URL.createObjectURL(blob);
      imageUrl.value = objectUrl;
    } catch {
      if (sequence === loadSequence) clearObjectUrl();
    }
  },
  { immediate: true }
);

onUnmounted(() => {
  loadSequence += 1;
  clearObjectUrl();
});
</script>

<style scoped>
.image {
  max-width: min(260px, 70vw);
  border-radius: 8px;
  display: block;
  margin-top: 6px;
  cursor: pointer;
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
