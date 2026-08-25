<template>
  <Teleport to="body">
    <div v-if="open" class="lightbox" @click.self="emit('close')">
      <button class="close" @click="emit('close')" :aria-label="t('common.cancel')">
        <ion-icon :icon="closeOutline" />
      </button>
      <img class="lightbox-image" :src="src" :alt="alt" />
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { IonIcon } from '@ionic/vue';
import { closeOutline } from 'ionicons/icons';
import { useI18n } from 'vue-i18n';

defineProps<{ src: string; alt: string; open: boolean }>();
const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
</script>

<style scoped>
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.92);
}
.close {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: #ffffff;
  font-size: 22px;
  cursor: pointer;
}
.close:active {
  background: rgba(255, 255, 255, 0.3);
}
.lightbox-image {
  max-width: 100vw;
  max-height: 100vh;
  object-fit: contain;
  border-radius: 0;
}
</style>
