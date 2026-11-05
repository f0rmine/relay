<template>
  <div ref="scroller" class="window" @scroll.passive="onScroll">
    <div v-if="pinnedMessage" class="pin-banner">
      <span class="pin-icon">📌</span>
      <span class="pin-text">{{ pinnedPreview }}</span>
    </div>
    <ion-button v-if="hasMore" class="older" fill="clear" size="small" @click="$emit('older')">{{ t('chat.loadOlder') }}</ion-button>
    <MessageBubble
      v-for="message in messages"
      :key="message.id"
      :ref="(el) => registerBubble(message.id, el)"
      :message="message"
      :own="message.sender_id === currentUserId"
      :sender-name="senderName(message.sender_id)"
      :participants="participants"
      :current-user-id="currentUserId"
      :pinned="conversation?.pinned_message_id === message.id"
      :highlight="highlightMessageId === message.id"
      @delete="$emit('delete-message', message.id)"
      @retry="$emit('retry-message', message.client_message_id || '')"
      @remove="$emit('remove-pending', message.client_message_id || '')"
      @edit="$emit('edit-message', $event)"
      @reply="$emit('reply-message', $event)"
      @react="(emoji) => $emit('react-message', { messageId: message.id, emoji })"
      @copy="(m) => $emit('copy-message', m)"
      @forward="$emit('forward-message', $event)"
      @pin="$emit('pin-message', $event)"
      @unpin="$emit('unpin-message', $event)"
      @open-image="openGallery"
      @open-reply="scrollToMessage"
      @highlight-done="emit('highlight-done')"
    />
    <TypingIndicator :visible="typing" :peer-name="peerName" />
    <ImageLightbox
      :images="galleryImages"
      :index="galleryIndex"
      :open="galleryOpen"
      @close="closeGallery"
      @update:index="galleryIndex = $event"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { IonButton } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import type { Message, User } from '@/api/types';
import MessageBubble from './MessageBubble.vue';
import TypingIndicator from './TypingIndicator.vue';
import ImageLightbox, { type LightboxImage } from './ImageLightbox.vue';

const props = defineProps<{
  messages: Message[];
  conversation?: { pinned_message_id?: string | null; kind?: string; title?: string | null };
  currentUserId?: string;
  participants?: User[];
  typing: boolean;
  peerName?: string;
  hasMore?: boolean;
  highlightMessageId?: string;
}>();
const emit = defineEmits<{
  older: [];
  'delete-message': [messageId: string];
  'retry-message': [clientMessageId: string];
  'remove-pending': [clientMessageId: string];
  'edit-message': [message: Message];
  'reply-message': [message: Message];
  'react-message': [payload: { messageId: string; emoji: string }];
  'copy-message': [message: Message];
  'forward-message': [message: Message];
  'pin-message': [message: Message];
  'unpin-message': [message: Message];
  'highlight-done': [];
}>();
const scroller = ref<HTMLElement | null>(null);
const preservingOlderScroll = ref(false);
const galleryOpen = ref(false);
const galleryImages = ref<LightboxImage[]>([]);
const galleryIndex = ref(0);
const bubbleRefs = new Map<string, InstanceType<typeof MessageBubble>>();
let latchTimer: number | null = null;
const { t } = useI18n();

function registerBubble(id: string, el: unknown) {
  if (el) bubbleRefs.set(id, el as InstanceType<typeof MessageBubble>);
  else bubbleRefs.delete(id);
}

const pinnedMessage = computed(
  () => props.messages.find((item) => item.id === props.conversation?.pinned_message_id) || null
);
const pinnedPreview = computed(() => {
  const target = pinnedMessage.value;
  if (!target) return '';
  if (target.undecryptable) return t('chat.messageUnavailable');
  return target.text || target.attachments?.[0]?.original_filename || t('chat.pinned');
});

const galleryObjectUrls: string[] = [];

function revokeGalleryUrls() {
  while (galleryObjectUrls.length) {
    const url = galleryObjectUrls.pop();
    if (url) URL.revokeObjectURL(url);
  }
}

async function openGallery(payload: { messageId: string; attachmentId: string }) {
  const images: Array<{ messageId: string; attachmentId: string }> = [];
  for (const message of props.messages) {
    if (message.deleted_at) continue;
    for (const attachment of message.attachments || []) {
      if (attachment.mime_type.startsWith('image/')) {
        images.push({ messageId: message.id, attachmentId: attachment.id });
      }
    }
  }
  const startIndex = Math.max(
    0,
    images.findIndex((entry) => entry.attachmentId === payload.attachmentId)
  );
  galleryIndex.value = startIndex;
  revokeGalleryUrls();
  galleryImages.value = images.map((entry) => ({ src: '', alt: entry.attachmentId }));
  galleryOpen.value = true;
  // Load thumbs first for fast preview, then upgrade the current image to full.
  const loaded = await Promise.all(
    images.map(async (entry) => {
      try {
        const blob = await import('@/api/client').then((mod) =>
          mod.apiBlob(`/attachments/${entry.attachmentId}/download?variant=thumb`)
        );
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
  // Upgrade the viewed image to full resolution in the background.
  const current = images[startIndex];
  if (current && galleryOpen.value) {
    try {
      const blob = await import('@/api/client').then((mod) =>
        mod.apiBlob(`/attachments/${current.attachmentId}/download`)
      );
      if (!galleryOpen.value) return;
      const url = URL.createObjectURL(blob);
      galleryObjectUrls.push(url);
      const next = [...galleryImages.value];
      if (next[startIndex]) next[startIndex] = { src: url, alt: current.attachmentId };
      galleryImages.value = next;
    } catch {
      // Thumb already shown; keep it.
    }
  }
}

function closeGallery() {
  galleryOpen.value = false;
  revokeGalleryUrls();
}

function senderName(senderId: string) {
  if (senderId === props.currentUserId) return t('common.you');
  return props.participants?.find((user) => user.id === senderId)?.display_name || t('common.user');
}

function scrollBottom() {
  nextTick(() => {
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  });
}

function scrollToMessage(messageId: string) {
  const element = scroller.value?.querySelector(`[data-message-id="${messageId}"]`);
  if (element instanceof HTMLElement) {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    return;
  }
  emit('older');
}

watch(
  () => props.highlightMessageId,
  (messageId) => {
    if (!messageId) return;
    nextTick(() => scrollToMessage(messageId));
  }
);

function onScroll() {
  if (!scroller.value || scroller.value.scrollTop >= 40 || !props.hasMore || preservingOlderScroll.value) {
    return;
  }
  preservingOlderScroll.value = true;
  previousScrollHeight = scroller.value.scrollHeight;
  latchTimer = window.setTimeout(() => {
    preservingOlderScroll.value = false;
  }, 5000);
  emit('older');
}

watch(
  () => props.messages.length,
  (length, previousLength) => {
    if (preservingOlderScroll.value) {
      if (length === previousLength) return;
      nextTick(() => {
        if (scroller.value && length > (previousLength ?? 0)) {
          scroller.value.scrollTop = scroller.value.scrollHeight - previousScrollHeight;
        }
        preservingOlderScroll.value = false;
        if (latchTimer !== null) {
          window.clearTimeout(latchTimer);
          latchTimer = null;
        }
      });
      return;
    }
    nearBottomScroll();
  }
);

function nearBottomScroll() {
  const el = scroller.value;
  if (!el) return;
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  if (nearBottom) scrollBottom();
}
onMounted(scrollBottom);
onUnmounted(revokeGalleryUrls);

let previousScrollHeight = 0;
</script>

<style scoped>
.window {
  position: relative;
  height: 100%;
  overflow-y: auto;
  padding: 10px 0 12px;
  background: var(--ion-background-color);
}
.pin-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 10px 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(64, 140, 255, 0.14);
  font-size: 13px;
}
.pin-icon {
  flex-shrink: 0;
}
.pin-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.older {
  display: block;
  margin: 0 auto 8px;
}
</style>
