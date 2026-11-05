<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-buttons slot="start">
          <ion-back-button :default-href="`/chat/${conversationId}`" text="" />
        </ion-buttons>
        <ion-title>{{ t('chat.mediaGallery') }}</ion-title>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <ErrorState v-if="error" :message="error" />
      <div v-if="!messages.length && !loading" class="empty">{{ t('chat.mediaEmpty') }}</div>
      <div v-if="loading && !messages.length" class="empty">{{ t('common.loading') }}</div>
      <div class="grid">
        <template v-for="message in messages" :key="message.id">
          <template v-for="attachment in mediaAttachments(message)" :key="attachment.id">
            <div v-if="attachment.mime_type.startsWith('video/')" class="grid-item">
              <VideoPlayer :attachment="attachment" />
            </div>
            <div
              v-else-if="attachment.mime_type.startsWith('image/')"
              class="grid-item"
              @click="openImage(message, attachment.id)"
            >
              <ImageMessage :attachment="attachment" @open="openImage(message, attachment.id)" />
            </div>
          </template>
        </template>
      </div>
      <ion-button
        v-if="hasMore"
        expand="block"
        fill="clear"
        :disabled="loading"
        @click="loadMore"
      >
        {{ t('chat.loadOlder') }}
      </ion-button>
      <ImageLightbox
        :images="galleryImages"
        :index="galleryIndex"
        :open="galleryOpen"
        @close="closeGallery"
        @update:index="galleryIndex = $event"
      />
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import {
  IonBackButton,
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonPage,
  IonTitle,
  IonToolbar
} from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { apiBlob, apiFetch, displayError } from '@/api/client';
import type { Attachment, Message } from '@/api/types';
import ErrorState from '@/components/ErrorState.vue';
import ImageLightbox, { type LightboxImage } from '@/components/chat/ImageLightbox.vue';
import ImageMessage from '@/components/chat/ImageMessage.vue';
import VideoPlayer from '@/components/chat/VideoPlayer.vue';

const route = useRoute();
const conversationId = String(route.params.id);
const messages = ref<Message[]>([]);
const cursor = ref<string | null>(null);
const hasMore = ref(false);
const loading = ref(false);
const error = ref('');
const galleryOpen = ref(false);
const galleryImages = ref<LightboxImage[]>([]);
const galleryIndex = ref(0);
const { t } = useI18n();

function mediaAttachments(message: Message): Attachment[] {
  return (message.attachments || []).filter(
    (a) => a.mime_type.startsWith('image/') || a.mime_type.startsWith('video/')
  );
}

async function fetchMedia() {
  loading.value = true;
  error.value = '';
  try {
    const params = new URLSearchParams({ type: 'media' });
    if (cursor.value) params.set('cursor', cursor.value);
    const response = await apiFetch<{
      items: Message[];
      next_cursor: string | null;
      has_more: boolean;
    }>(`/conversations/${conversationId}/messages?${params.toString()}`);
    const items = [...response.items].reverse();
    messages.value = cursor.value ? [...items, ...messages.value] : items;
    cursor.value = response.next_cursor;
    hasMore.value = response.has_more;
  } catch (err: unknown) {
    error.value = displayError(err, t('chat.mediaLoadFailed'));
  } finally {
    loading.value = false;
  }
}

async function loadMore() {
  await fetchMedia();
}

onMounted(() => {
  void fetchMedia();
});

const galleryObjectUrls: string[] = [];

function revokeGalleryUrls() {
  while (galleryObjectUrls.length) {
    const url = galleryObjectUrls.pop();
    if (url) URL.revokeObjectURL(url);
  }
}

async function openImage(_message: Message, attachmentId: string) {
  const images: Array<{ attachmentId: string }> = [];
  for (const message of messages.value) {
    if (message.deleted_at) continue;
    for (const attachment of message.attachments || []) {
      if (attachment.mime_type.startsWith('image/')) {
        images.push({ attachmentId: attachment.id });
      }
    }
  }
  const startIndex = Math.max(
    0,
    images.findIndex((entry) => entry.attachmentId === attachmentId)
  );
  galleryIndex.value = startIndex;
  revokeGalleryUrls();
  galleryImages.value = images.map((entry) => ({ src: '', alt: entry.attachmentId }));
  galleryOpen.value = true;
  const loaded = await Promise.all(
    images.map(async (entry) => {
      try {
        const blob = await apiBlob(`/attachments/${entry.attachmentId}/download?variant=thumb`);
        const url = URL.createObjectURL(blob);
        if (!galleryOpen.value) {
          URL.revokeObjectURL(url);
          return { src: '', alt: entry.attachmentId };
        }
        galleryObjectUrls.push(url);
        return { src: url, alt: entry.attachmentId };
      } catch {
        return { src: '', alt: entry.attachmentId };
      }
    })
  );
  if (galleryOpen.value) galleryImages.value = loaded;
}

function closeGallery() {
  galleryOpen.value = false;
  revokeGalleryUrls();
}
</script>

<style scoped>
.page-content {
  --padding: 10px;
}
.empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--relay-muted);
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.grid-item {
  overflow: hidden;
  border-radius: 8px;
  cursor: pointer;
}
.grid-item :deep(.image) {
  width: 100%;
  max-width: none;
  margin-top: 0;
  aspect-ratio: 1;
  object-fit: cover;
}
.grid-item :deep(.video-player) {
  max-width: none;
}
.grid-item :deep(.video) {
  max-height: 160px;
}
</style>
