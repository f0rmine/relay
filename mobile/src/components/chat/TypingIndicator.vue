<template>
  <div v-if="visible" class="typing">
    <span class="dots">
      <span class="dot" /><span class="dot" /><span class="dot" />
    </span>
    {{ label }}
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps<{ visible: boolean; peerName?: string }>();
const { t } = useI18n();

const label = computed(() =>
  props.peerName
    ? t('chat.typingUser', { name: props.peerName })
    : t('chat.typing')
);
</script>

<style scoped>
.typing {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 14px 8px;
  color: var(--relay-muted);
  font-size: 13px;
}
.dots {
  display: inline-flex;
  gap: 3px;
}
.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--relay-muted);
  animation: bounce 1.2s infinite ease-in-out;
}
.dot:nth-child(1) { animation-delay: 0s; }
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-4px); }
}
</style>
