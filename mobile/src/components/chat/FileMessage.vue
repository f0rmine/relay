<template>
  <button class="file" type="button" :class="{ failed }" :disabled="loading" @click="openFile">
    <ion-icon :icon="documentAttachOutline" />
    <span>{{ loading ? t('chat.opening') : failed ? t('chat.downloadFailed') : attachment.original_filename }}</span>
  </button>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { IonIcon } from '@ionic/vue';
import { documentAttachOutline } from 'ionicons/icons';
import { useI18n } from 'vue-i18n';
import { apiBlob } from '@/api/client';
import type { Attachment } from '@/api/types';

const props = defineProps<{ attachment: Attachment }>();
const loading = ref(false);
const failed = ref(false);
const { t } = useI18n();

async function openFile() {
  if (loading.value) return;
  failed.value = false;
  if (props.attachment.id.startsWith('local-attachment-')) {
    window.open(props.attachment.public_url, '_blank', 'noopener,noreferrer');
    return;
  }
  loading.value = true;
  try {
    const blob = await apiBlob(`/attachments/${props.attachment.id}/download`);
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank', 'noopener,noreferrer');
    window.setTimeout(() => URL.revokeObjectURL(url), 30000);
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
}
</script>
<style scoped>
.file.failed span {
  color: #ff8a80;
}
</style>

<style scoped>
.file {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ion-color-primary);
  font: inherit;
  text-align: left;
}
.file:disabled {
  opacity: 0.65;
}
</style>
