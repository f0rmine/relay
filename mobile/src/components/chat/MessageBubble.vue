<template>
  <div class="row" :class="{ own }" :data-message-id="message.id">
    <div
      class="bubble"
      :class="{ pending: isPending, failed: isFailed, deleted: message.deleted_at, highlighted: highlight }"
      @touchstart="startPress"
      @touchend="cancelPress"
      @touchcancel="cancelPress"
      @contextmenu.prevent="openActions"
    >
      <div v-if="message.reply_to" class="quoted" @click.stop="emit('open-reply', message.reply_to.id)">
        <span class="quoted-name">{{ replyAuthorName }}</span>
        <span class="quoted-text">{{ quotedPreview }}</span>
      </div>
      <div v-if="message.deleted_at" class="deleted-state">
        <span class="deleted-icon">×</span>
        <em>{{ t('chat.deletedBy', { name: senderName }) }}</em>
      </div>
      <template v-else>
        <p v-if="message.undecryptable" class="undecryptable">{{ t('chat.messageUnavailable') }}</p>
        <p v-else-if="message.text">{{ message.text }}</p>
        <template v-for="attachment in message.attachments" :key="attachment.id">
          <VoiceNotePlayer
            v-if="attachment.mime_type.startsWith('audio/') && !attachment.id.startsWith('local-')"
            :attachment-id="attachment.id"
          />
          <ImageMessage
            v-else-if="attachment.mime_type.startsWith('image/')"
            :attachment="attachment"
            @open="emit('open-image', { messageId: message.id, attachmentId: attachment.id })"
          />
          <FileMessage v-else :attachment="attachment" />
        </template>
      </template>
      <div v-if="reactionChips.length" class="chips">
        <button
          v-for="chip in reactionChips"
          :key="chip.emoji"
          class="chip"
          :class="{ mine: chip.mine }"
          type="button"
          @click.stop="emit('react', chip.emoji)"
        >
          {{ chip.emoji }} {{ chip.count }}
        </button>
      </div>
      <div class="time">
        {{ d(new Date(message.created_at), 'time') }}
        <span v-if="message.edited_at" class="edited">{{ t('chat.edited') }}</span>
        <span v-if="message.delivery_state === 'queued'">{{ t('chat.queued') }}</span>
        <span v-else-if="message.delivery_state === 'sending'">{{ t('chat.sending') }}</span>
        <span v-else-if="message.delivery_state === 'failed'">{{ t('chat.failed') }}</span>
        <span v-else-if="own">{{ message.read_by.length ? '✓✓' : '✓' }}</span>
      </div>
    </div>
    <ion-action-sheet
      :is-open="actionsOpen"
      :header="t('chat.actionTitle')"
      :buttons="actionButtons"
      css-class="relay-message-actions"
      @didDismiss="actionsOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { IonActionSheet } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import type { Message } from '@/api/types';
import FileMessage from './FileMessage.vue';
import ImageMessage from './ImageMessage.vue';
import VoiceNotePlayer from './VoiceNotePlayer.vue';

const props = defineProps<{
  message: Message;
  own: boolean;
  senderName: string;
  participants?: Array<{ id: string; display_name: string; username: string }>;
  currentUserId?: string;
  pinned?: boolean;
  highlight?: boolean;
}>();
const emit = defineEmits<{
  delete: [];
  retry: [];
  remove: [];
  edit: [message: Message];
  reply: [message: Message];
  react: [emoji: string];
  copy: [message: Message];
  forward: [message: Message];
  pin: [message: Message];
  unpin: [message: Message];
  'open-image': [payload: { messageId: string; attachmentId: string }];
  'open-reply': [messageId: string];
  'highlight-done': [];
}>();

const actionsOpen = ref(false);
let pressTimer: number | undefined;
const { d, t } = useI18n();

const QUICK_EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🔥'];

const isPending = computed(() => props.message.id.startsWith('pending-'));
const isFailed = computed(() => props.message.delivery_state === 'failed');
const canDelete = computed(() => props.own && !isPending.value && !props.message.deleted_at);
const canEdit = computed(
  () => props.own && !isPending.value && !props.message.deleted_at && !!props.message.text
);
const reactionChips = computed(() =>
  (props.message.reactions || []).map((group) => ({
    emoji: group.emoji,
    count: group.user_ids.length,
    mine: Boolean(props.currentUserId && group.user_ids.includes(props.currentUserId))
  }))
);
const replyAuthorName = computed(() => {
  if (!props.message.reply_to) return '';
  const author = props.participants?.find((user) => user.id === props.message.reply_to?.sender_id);
  const ownReply = props.message.reply_to.sender_id === props.currentUserId;
  return ownReply ? t('common.you') : author?.display_name || t('common.user');
});
const quotedPreview = computed(() => {
  const target = props.message.reply_to;
  if (!target) return '';
  if (target.undecryptable) return t('chat.messageUnavailable');
  return target.text || t('chat.imageUnavailable');
});
const myReaction = computed(() => {
  if (!props.currentUserId) return null;
  const group = (props.message.reactions || []).find((entry) =>
    entry.user_ids.includes(props.currentUserId as string)
  );
  return group ? group.emoji : null;
});

const actionButtons = computed(() => {
  if (isFailed.value) {
    return [
      { text: t('chat.retry'), handler: () => emit('retry') },
      { text: t('chat.removeFailed'), role: 'destructive', handler: () => emit('remove') },
      { text: t('common.cancel'), role: 'cancel' }
    ];
  }
  const buttons: Array<{ text: string; handler?: () => void; role?: string }> = [
    ...QUICK_EMOJIS.map((emoji) => ({
      text: myReaction.value === emoji ? `${emoji} ${t('chat.reacted')}` : emoji,
      handler: () => emit('react', emoji)
    })),
    ...(canEdit.value ? [{ text: `✏️ ${t('chat.editMessage')}`, handler: () => emit('edit', props.message) }] : []),
    { text: `↩️ ${t('chat.reply')}`, handler: () => emit('reply', props.message) },
    ...(props.message.text
      ? [{ text: `📋 ${t('chat.copy')}`, handler: () => emit('copy', props.message) }]
      : []),
    { text: `📤 ${t('chat.forward')}`, handler: () => emit('forward', props.message) },
    ...(props.pinned
      ? [{ text: `📌 ${t('chat.unpin')}`, handler: () => emit('unpin', props.message) }]
      : [{ text: `📌 ${t('chat.pin')}`, handler: () => emit('pin', props.message) }]),
    ...(canDelete.value
      ? [{ text: t('chat.deleteEveryone'), role: 'destructive', handler: () => emit('delete') }]
      : []),
    { text: t('common.cancel'), role: 'cancel' }
  ];
  return buttons;
});

function openActions() {
  if (isPending.value) return;
  actionsOpen.value = true;
}

function startPress() {
  if (isPending.value) return;
  cancelPress();
  pressTimer = window.setTimeout(openActions, 500);
}

function cancelPress() {
  if (pressTimer) window.clearTimeout(pressTimer);
  pressTimer = undefined;
}

watch(
  () => props.highlight,
  (value) => {
    if (!value) return;
    window.setTimeout(() => emit('highlight-done'), 1600);
  }
);
</script>

<style scoped>
.row {
  display: flex;
  justify-content: flex-start;
  padding: 2px 10px;
}
.row.own {
  justify-content: flex-end;
}
.bubble {
  max-width: min(78%, 560px);
  border-radius: 10px 10px 10px 4px;
  padding: 7px 9px 5px;
  background: var(--relay-bubble-peer);
  color: var(--ion-text-color);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.18);
}
.own .bubble {
  background: var(--relay-bubble-own);
  border-radius: 10px 10px 4px 10px;
}
.bubble.pending {
  opacity: 0.7;
}
.bubble.failed {
  border: 1px solid #e66b6b;
  opacity: 1;
}
.bubble.deleted {
  background: var(--relay-border);
  color: var(--ion-text-color);
}
.bubble.highlighted {
  animation: flash-highlight 1.5s ease-out;
}
@keyframes flash-highlight {
  0%,
  40% {
    box-shadow: 0 0 0 3px #ffd54f inset;
  }
  100% {
    box-shadow: 0 1px 0 rgba(0, 0, 0, 0.18);
  }
}
.quoted {
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin-bottom: 4px;
  padding: 4px 8px;
  border-left: 3px solid var(--ion-color-primary);
  background: var(--relay-border);
  border-radius: 4px;
  cursor: pointer;
}
.quoted-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--ion-color-primary);
}
.quoted-text {
  font-size: 13px;
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 46vw;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.chip {
  border: none;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--relay-border);
  color: inherit;
  font-size: 12px;
  cursor: pointer;
}
.chip.mine {
  background: rgba(64, 140, 255, 0.45);
}
p {
  margin: 0;
  line-height: 1.32;
}
.undecryptable {
  color: var(--relay-muted);
  font-style: italic;
}
em {
  color: var(--ion-text-color);
  font-style: normal;
  font-weight: 500;
}
.deleted-state {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}
.deleted-icon {
  display: inline-grid;
  width: 18px;
  height: 18px;
  place-items: center;
  border-radius: 999px;
  background: var(--relay-border);
  color: var(--ion-text-color);
  font-size: 16px;
  line-height: 1;
}
:global(.relay-message-actions) {
  --background: var(--relay-panel);
  --color: var(--ion-text-color);
  --button-color: var(--ion-text-color);
  --button-background: var(--relay-panel);
  --button-background-hover: var(--relay-border);
  --button-background-activated: var(--relay-border);
}
:global(.relay-message-actions .action-sheet-title),
:global(.relay-message-actions .action-sheet-button),
:global(.relay-message-actions .action-sheet-button-inner) {
  color: var(--ion-text-color) !important;
}
:global(.relay-message-actions .action-sheet-destructive) {
  color: #e66b6b !important;
}
.time {
  margin-top: 4px;
  text-align: right;
  font-size: 11px;
  color: var(--relay-muted);
}
.edited {
  margin-right: 4px;
  font-style: italic;
}
</style>
