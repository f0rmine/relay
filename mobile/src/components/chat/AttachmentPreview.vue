<template>
  <div v-if="file" class="preview">
    <span class="file-name">{{ file.name }}</span>
    <ion-button size="small" fill="clear" @click="$emit('clear')">{{ t('chat.removeAttachment') }}</ion-button>
  </div>
</template>

<script setup lang="ts">
import { IonButton } from '@ionic/vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

defineProps<{ file: File | null }>();
defineEmits<{ clear: [] }>();
</script>

<style scoped>
.preview {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 8px 10px 0;
  padding: 8px 10px;
  border: 1px solid rgba(42, 171, 238, 0.18);
  border-radius: 12px;
  background: rgba(42, 171, 238, 0.08);
  font-size: 13px;
  color: var(--relay-muted);
}
.file-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
