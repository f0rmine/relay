<template>
  <div
    class="video-player"
    data-testid="video-player"
    :data-state="state"
    @touchstart.stop
    @touchmove.stop
    @touchend.stop
    @contextmenu.stop
  >
    <video
      v-if="state === 'ready' && videoUrl"
      data-testid="video-element"
      class="video"
      :src="videoUrl"
      controls
      playsinline
      preload="metadata"
    />
    <div v-else-if="state === 'loading'" class="video-tile loading-tile" data-testid="video-progress">
      <svg class="progress-ring" width="56" height="56" viewBox="0 0 56 56" aria-hidden="true">
        <circle class="ring-track" cx="28" cy="28" r="24" fill="none" stroke-width="4" />
        <circle
          class="ring-bar"
          cx="28"
          cy="28"
          r="24"
          fill="none"
          stroke-width="4"
          stroke-linecap="round"
          :stroke-dasharray="ringCircumference"
          :stroke-dashoffset="ringDashOffset"
        />
      </svg>
      <span class="progress-text">{{ progressLabel }}</span>
      <span class="file-meta">{{ attachment.original_filename }} · {{ formattedSize }}</span>
    </div>
    <div v-else class="video-tile idle-tile" data-testid="video-idle">
      <span class="tile-icon" aria-hidden="true"><ion-icon :icon="filmOutline" /></span>
      <span class="file-meta strong">{{ attachment.original_filename }}</span>
      <span class="file-meta">{{ formattedSize }}</span>
      <span v-if="failed" class="error-text">{{ t('chat.downloadFailed') }}</span>
      <ion-button
        data-testid="video-download-button"
        class="download-button"
        shape="round"
        :aria-label="t('chat.downloadVideo')"
        @click.stop="startDownload"
        @touchstart.stop
        @touchend.stop
      >
        <ion-icon slot="icon-only" :icon="downloadOutline" />
      </ion-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue';
import { IonButton, IonIcon } from '@ionic/vue';
import { downloadOutline, filmOutline } from 'ionicons/icons';
import { useI18n } from 'vue-i18n';
import { apiUrl } from '@/config/env';
import { refreshTokens } from '@/api/client';
import { getAccessToken } from '@/services/auth-storage';
import type { Attachment } from '@/api/types';

const props = defineProps<{ attachment: Attachment }>();
const { t } = useI18n();

type PlayerState = 'idle' | 'loading' | 'ready';
const state = ref<PlayerState>('idle');
const videoUrl = ref('');
const downloadedBytes = ref(0);
const totalBytes = ref(0);
const failed = ref(false);

let objectUrl = '';
let ownsObjectUrl = false;
let abortController: AbortController | null = null;
let downloadSequence = 0;

const RING_RADIUS = 24;
const ringCircumference = 2 * Math.PI * RING_RADIUS;
const progressRatio = computed(() => {
  if (totalBytes.value > 0) return Math.min(1, Math.max(0, downloadedBytes.value / totalBytes.value));
  return 0;
});
const ringDashOffset = computed(() => ringCircumference * (1 - progressRatio.value));
const progressLabel = computed(() => {
  if (totalBytes.value > 0) return `${Math.round(progressRatio.value * 100)}%`;
  return formatBytes(downloadedBytes.value);
});
const formattedSize = computed(() => formatBytes(props.attachment.file_size || totalBytes.value || 0));

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / Math.pow(1024, index);
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
}

function clearObjectUrl() {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl);
    objectUrl = '';
    ownsObjectUrl = false;
  }
  videoUrl.value = '';
}

function useLocalUrl() {
  // Locally pending attachments expose an object/blob URL via public_url.
  if (props.attachment.public_url) {
    videoUrl.value = props.attachment.public_url;
    state.value = 'ready';
  }
}

async function authorizedFetch(signal: AbortSignal): Promise<Response> {
  const headers = new Headers();
  const accessToken = await getAccessToken();
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  let response = await fetch(apiUrl(`/attachments/${props.attachment.id}/download`), { headers, signal });
  if (response.status === 401) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      headers.set('Authorization', `Bearer ${refreshed.access_token}`);
      response = await fetch(apiUrl(`/attachments/${props.attachment.id}/download`), { headers, signal });
    }
  }
  return response;
}

async function startDownload() {
  if (state.value === 'loading') return;
  // Local attachments are already playable via public_url.
  if (props.attachment.id.startsWith('local-')) {
    failed.value = false;
    useLocalUrl();
    if (state.value !== 'ready') failed.value = true;
    return;
  }
  if (state.value === 'ready' && videoUrl.value) return;

  const sequence = ++downloadSequence;
  abortController?.abort();
  abortController = new AbortController();
  const signal = abortController.signal;
  state.value = 'loading';
  failed.value = false;
  downloadedBytes.value = 0;
  totalBytes.value = props.attachment.file_size || 0;
  clearObjectUrl();

  try {
    const response = await authorizedFetch(signal);
    if (sequence !== downloadSequence) return;
    if (!response.ok) throw new Error(`download failed: ${response.status}`);

    const contentLength = Number(response.headers.get('content-length'));
    if (Number.isFinite(contentLength) && contentLength > 0) totalBytes.value = contentLength;

    const chunks: BlobPart[] = [];
    if (!response.body) {
      const blob = await response.blob();
      chunks.push(blob);
      downloadedBytes.value = blob.size;
      if (!totalBytes.value) totalBytes.value = blob.size;
    } else {
      const reader = response.body.getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) {
          chunks.push(value);
          downloadedBytes.value += value.byteLength;
        }
        if (sequence !== downloadSequence) {
          try { await reader.cancel(); } catch { /* ignore */ }
          reader.releaseLock();
          return;
        }
      }
    }

    if (sequence !== downloadSequence) return;
    const url = URL.createObjectURL(new Blob(chunks, { type: props.attachment.mime_type }));
    objectUrl = url;
    ownsObjectUrl = true;
    videoUrl.value = url;
    state.value = 'ready';
  } catch {
    if (sequence !== downloadSequence) return;
    if (signal.aborted) return;
    failed.value = true;
    state.value = 'idle';
    clearObjectUrl();
  } finally {
    if (sequence === downloadSequence) abortController = null;
  }
}

// Local preview (pending upload) should be playable without a download step.
if (props.attachment.id.startsWith('local-') && props.attachment.public_url) {
  useLocalUrl();
}

onUnmounted(() => {
  downloadSequence += 1;
  abortController?.abort();
  if (ownsObjectUrl) clearObjectUrl();
});
</script>

<style scoped>
.video-player {
  margin-top: 6px;
  max-width: min(280px, 72vw);
}
.video {
  display: block;
  width: 100%;
  max-height: 240px;
  border-radius: 8px;
  background: #000;
}
.video-tile {
  position: relative;
  display: grid;
  place-items: center;
  gap: 4px;
  width: 100%;
  min-height: 132px;
  padding: 18px 14px;
  border-radius: 8px;
  overflow: hidden;
  text-align: center;
  color: #eef4ff;
}
.idle-tile {
  background:
    radial-gradient(circle at 30% 20%, rgba(64, 140, 255, 0.35), transparent 55%),
    radial-gradient(circle at 75% 80%, rgba(42, 171, 238, 0.28), transparent 50%),
    linear-gradient(135deg, #16233a, #0d1526);
}
.idle-tile::before {
  content: '';
  position: absolute;
  inset: -12px;
  background:
    repeating-linear-gradient(115deg, rgba(255, 255, 255, 0.05) 0 18px, transparent 18px 36px);
  filter: blur(6px);
  pointer-events: none;
}
.loading-tile {
  background: linear-gradient(135deg, #16233a, #0d1526);
}
.tile-icon {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 72px;
  color: rgba(255, 255, 255, 0.08);
  pointer-events: none;
}
.file-meta {
  position: relative;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: rgba(238, 244, 255, 0.82);
}
.file-meta.strong {
  font-weight: 600;
  color: #fff;
}
.error-text {
  position: relative;
  font-size: 12px;
  color: #ff9a9a;
}
.progress-ring {
  position: relative;
  transform: rotate(-90deg);
}
.ring-track {
  stroke: rgba(255, 255, 255, 0.18);
}
.ring-bar {
  stroke: var(--ion-color-primary, #2aabee);
  transition: stroke-dashoffset 0.15s linear;
}
.progress-text {
  position: relative;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}
.download-button {
  position: relative;
  --background: rgba(255, 255, 255, 0.16);
  --background-activated: rgba(255, 255, 255, 0.26);
  --color: #fff;
  --padding-start: 0;
  --padding-end: 0;
  width: 44px;
  height: 44px;
  margin-top: 6px;
}
.download-button ion-icon {
  font-size: 22px;
}
</style>
