<template>
  <div class="voice-player">
    <ion-button fill="clear" size="small" class="play" @click="toggle">
      <ion-icon :icon="playing ? pauseOutline : playOutline" />
    </ion-button>
    <input
      class="seek"
      type="range"
      min="0"
      max="1000"
      :value="progress"
      :disabled="!ready"
      @input="onSeek"
    />
    <span class="time">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue';
import { IonButton, IonIcon } from '@ionic/vue';
import { pauseOutline, playOutline } from 'ionicons/icons';
import { apiBlob } from '@/api/client';
import { useI18n } from 'vue-i18n';

const props = defineProps<{ attachmentId: string }>();
const { t } = useI18n();
const audio = ref<HTMLAudioElement | null>(null);
const playing = ref(false);
const ready = ref(false);
const progress = ref(0);
const duration = ref(0);
const current = ref(0);
let objectUrl = '';

const label = computed(() => {
  const total = duration.value || current.value || 0;
  const seconds = Math.floor(total % 60);
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
});

async function toggle() {
  if (!audio.value) {
    try {
      const blob = await apiBlob(`/attachments/${props.attachmentId}/download`);
      objectUrl = URL.createObjectURL(blob);
      const element = new Audio(objectUrl);
      element.addEventListener('loadedmetadata', () => {
        duration.value = element.duration || 0;
        ready.value = true;
      });
      element.addEventListener('timeupdate', () => {
        current.value = element.currentTime;
        if (element.duration) progress.value = Math.round((element.currentTime / element.duration) * 1000);
      });
      element.addEventListener('ended', () => {
        playing.value = false;
        progress.value = 0;
        current.value = 0;
      });
      audio.value = element;
    } catch {
      return;
    }
  }
  if (playing.value) {
    audio.value.pause();
    playing.value = false;
  } else {
    void audio.value.play();
    playing.value = true;
  }
}

function onSeek(event: Event) {
  const value = Number((event.target as HTMLInputElement).value);
  progress.value = value;
  if (audio.value && duration.value) audio.value.currentTime = (value / 1000) * duration.value;
}

onUnmounted(() => {
  audio.value?.pause();
  if (objectUrl) URL.revokeObjectURL(objectUrl);
});
</script>

<style scoped>
.voice-player {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 180px;
  margin-top: 6px;
}
.seek {
  flex: 1;
  accent-color: var(--ion-color-primary);
}
.time {
  font-size: 12px;
  color: var(--relay-muted);
}
</style>
