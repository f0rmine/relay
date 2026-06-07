<template>
  <div class="row" :class="{ own }">
    <div
      class="bubble"
      :class="{ pending: isPending, deleted: message.deleted_at }"
      @touchstart="startPress"
      @touchend="cancelPress"
      @touchcancel="cancelPress"
      @contextmenu.prevent="openActions"
    >
      <div v-if="message.deleted_at" class="deleted-state">
        <span class="deleted-icon">×</span>
        <em>{{ senderName }} deleted message</em>
      </div>
      <template v-else>
        <p v-if="message.text">{{ message.text }}</p>
        <template v-for="attachment in message.attachments" :key="attachment.id">
          <ImageMessage v-if="attachment.mime_type.startsWith('image/')" :attachment="attachment" />
          <FileMessage v-else :attachment="attachment" />
        </template>
      </template>
      <div class="time">
        {{ new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}
        <span v-if="isPending">sending</span>
        <span v-else-if="own">{{ message.read_by.length ? '✓✓' : '✓' }}</span>
      </div>
    </div>
    <ion-action-sheet
      :is-open="actionsOpen"
      header="Message"
      :buttons="actionButtons"
      @didDismiss="actionsOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { IonActionSheet } from '@ionic/vue';
import type { Message } from '@/api/types';
import FileMessage from './FileMessage.vue';
import ImageMessage from './ImageMessage.vue';

const props = defineProps<{ message: Message; own: boolean; senderName: string }>();
const emit = defineEmits<{ delete: [] }>();
const actionsOpen = ref(false);
let pressTimer: number | undefined;

const isPending = computed(() => props.message.id.startsWith('pending-'));
const canDelete = computed(() => props.own && !isPending.value && !props.message.deleted_at);
const actionButtons = computed(() => [
  {
    text: 'Delete for everyone',
    role: 'destructive',
    handler: () => emit('delete')
  },
  {
    text: 'Cancel',
    role: 'cancel'
  }
]);

function openActions() {
  if (!canDelete.value) return;
  actionsOpen.value = true;
}

function startPress() {
  if (!canDelete.value) return;
  cancelPress();
  pressTimer = window.setTimeout(openActions, 500);
}

function cancelPress() {
  if (pressTimer) window.clearTimeout(pressTimer);
  pressTimer = undefined;
}
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
.bubble.deleted {
  background: rgba(39, 54, 68, 0.72);
  color: var(--relay-muted);
}
p {
  margin: 0;
  line-height: 1.32;
}
em {
  color: var(--relay-muted);
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
  background: rgba(143, 163, 181, 0.18);
  color: #a9bbcb;
  font-size: 16px;
  line-height: 1;
}
.time {
  margin-top: 4px;
  text-align: right;
  font-size: 11px;
  color: #b8c8da;
  white-space: nowrap;
}
</style>
