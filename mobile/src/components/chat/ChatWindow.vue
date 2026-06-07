<template>
  <div ref="scroller" class="window" @scroll.passive="onScroll">
    <ion-button v-if="hasMore" class="older" fill="clear" size="small" @click="$emit('older')">Load older</ion-button>
    <MessageBubble
      v-for="message in messages"
      :key="message.id"
      :message="message"
      :own="message.sender_id === currentUserId"
    />
    <TypingIndicator :visible="typing" />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue';
import { IonButton } from '@ionic/vue';
import type { Message } from '@/api/types';
import MessageBubble from './MessageBubble.vue';
import TypingIndicator from './TypingIndicator.vue';

const props = defineProps<{ messages: Message[]; currentUserId?: string; typing: boolean; hasMore?: boolean }>();
const emit = defineEmits<{ older: [] }>();
const scroller = ref<HTMLElement | null>(null);
const preservingOlderScroll = ref(false);
let previousScrollHeight = 0;

function scrollBottom() {
  nextTick(() => {
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  });
}

function onScroll() {
  if (!scroller.value || scroller.value.scrollTop >= 40 || !props.hasMore || preservingOlderScroll.value) {
    return;
  }
  preservingOlderScroll.value = true;
  previousScrollHeight = scroller.value.scrollHeight;
  emit('older');
  window.setTimeout(() => {
    preservingOlderScroll.value = false;
  }, 1500);
}

watch(
  () => props.messages.length,
  () => {
    if (preservingOlderScroll.value) {
      nextTick(() => {
        if (scroller.value) {
          scroller.value.scrollTop = scroller.value.scrollHeight - previousScrollHeight;
        }
        preservingOlderScroll.value = false;
      });
      return;
    }
    scrollBottom();
  }
);
onMounted(scrollBottom);
</script>

<style scoped>
.window {
  height: 100%;
  overflow-y: auto;
  padding: 10px 0 12px;
  background: #0e1621;
}
.older {
  display: block;
  margin: 0 auto 8px;
}
</style>
