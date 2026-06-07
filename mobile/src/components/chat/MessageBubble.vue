<template>
  <div class="row" :class="{ own }">
    <div class="bubble" :class="{ pending: message.id.startsWith('pending-') }">
      <em v-if="message.deleted_at">Message deleted</em>
      <template v-else>
        <p v-if="message.text">{{ message.text }}</p>
        <template v-for="attachment in message.attachments" :key="attachment.id">
          <ImageMessage v-if="attachment.mime_type.startsWith('image/')" :attachment="attachment" />
          <FileMessage v-else :attachment="attachment" />
        </template>
      </template>
      <div class="time">
        {{ new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}
        <span v-if="message.id.startsWith('pending-')">sending</span>
        <span v-else-if="own">{{ message.read_by.length ? '✓✓' : '✓' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Message } from '@/api/types';
import FileMessage from './FileMessage.vue';
import ImageMessage from './ImageMessage.vue';

defineProps<{ message: Message; own: boolean }>();
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
p {
  margin: 0;
  line-height: 1.32;
}
em {
  color: var(--relay-muted);
}
.time {
  margin-top: 4px;
  text-align: right;
  font-size: 11px;
  color: #b8c8da;
  white-space: nowrap;
}
</style>
