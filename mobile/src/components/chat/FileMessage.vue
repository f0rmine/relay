<template>
  <button class="file" type="button" :disabled="loading" @click="openFile">
    <ion-icon :icon="documentAttachOutline" />
    <span>{{ loading ? t('chat.opening') : attachment.original_filename }}</span>
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
const { t } = useI18n();

async function openFile() {
  if (loading.value) return;
  loading.value = true;
  try {
    const blob = await apiBlob(`/attachments/${props.attachment.id}/download`);
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank', 'noopener,noreferrer');
    window.setTimeout(() => URL.revokeObjectURL(url), 30000);
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.file {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #b7ddff;
  font: inherit;
  text-align: left;
}
.file:disabled {
  opacity: 0.65;
}
</style>
