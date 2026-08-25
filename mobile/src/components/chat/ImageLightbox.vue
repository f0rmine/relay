<template>
  <Teleport to="body">
    <div v-if="open && images.length" class="lightbox" @click.self="emit('close')">
      <button class="close" @click="emit('close')" :aria-label="t('common.cancel')">
        <ion-icon :icon="closeOutline" />
      </button>
      <button v-if="images.length > 1" class="nav prev" @click.stop="step(-1)" :aria-label="t('common.previous')">
        <ion-icon :icon="chevronBackOutline" />
      </button>
      <img class="lightbox-image" :src="images[index]?.src" :alt="images[index]?.alt" @click.stop />
      <button v-if="images.length > 1" class="nav next" @click.stop="step(1)" :aria-label="t('common.next')">
        <ion-icon :icon="chevronForwardOutline" />
      </button>
      <div v-if="images.length > 1" class="counter">{{ index + 1 }} / {{ images.length }}</div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { watch } from 'vue';
import { IonIcon } from '@ionic/vue';
import { chevronBackOutline, chevronForwardOutline, closeOutline } from 'ionicons/icons';
import { useI18n } from 'vue-i18n';

export interface LightboxImage {
  src: string;
  alt: string;
}

const props = defineProps<{ images: LightboxImage[]; index: number; open: boolean }>();
const emit = defineEmits<{ close: []; 'update:index': [index: number] }>();
const { t } = useI18n();

function step(delta: number) {
  const next = (props.index + delta + props.images.length) % props.images.length;
  emit('update:index', next);
}

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'ArrowLeft') step(-1);
      else if (event.key === 'ArrowRight') step(1);
      else if (event.key === 'Escape') emit('close');
    };
    window.addEventListener('keydown', handler);
    const stop = (): void => window.removeEventListener('keydown', handler);
    watch(
      () => props.open,
      (stillOpen) => {
        if (!stillOpen) stop();
      }
    );
  }
);
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
  z-index: 2;
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
.nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
  display: grid;
  place-items: center;
  width: 44px;
  height: 64px;
  border: none;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  font-size: 26px;
  cursor: pointer;
}
.nav.prev {
  left: 6px;
}
.nav.next {
  right: 6px;
}
.counter {
  position: absolute;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
}
.lightbox-image {
  max-width: 100vw;
  max-height: 100vh;
  object-fit: contain;
}
</style>
