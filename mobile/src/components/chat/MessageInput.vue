<template>
  <div class="composer">
    <AttachmentPreview :file="file" @clear="file = null" />
    <div class="bar">
      <ion-button fill="clear" class="attach-button" shape="round" @click="pick" aria-label="Attach file">
        <ion-icon :icon="attachOutline" />
      </ion-button>
      <input ref="fileInput" class="hidden" type="file" @change="onFile" />
      <div class="input-shell">
        <textarea
          ref="textInput"
          v-model="text"
          rows="1"
          placeholder="Message"
          autocomplete="off"
          autocapitalize="sentences"
          spellcheck="false"
          enterkeyhint="send"
          @input="resizeInput"
          @focus="$emit('typing', true)"
          @blur="$emit('typing', false)"
        ></textarea>
      </div>
      <ion-button class="send-button" shape="round" :disabled="!canSend || sending" @click="submit" aria-label="Send message">
        <ion-icon :icon="paperPlaneOutline" />
      </ion-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { IonButton, IonIcon } from '@ionic/vue';
import { attachOutline, paperPlaneOutline } from 'ionicons/icons';
import AttachmentPreview from './AttachmentPreview.vue';

const emit = defineEmits<{ send: [text: string, file: File | null]; typing: [active: boolean] }>();
defineProps<{ sending?: boolean }>();
const text = ref('');
const file = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const textInput = ref<HTMLTextAreaElement | null>(null);
const canSend = computed(() => text.value.trim().length > 0 || file.value);

function pick() {
  fileInput.value?.click();
}

function onFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] || null;
}

function resizeInput() {
  const input = textInput.value;
  if (!input) return;
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 110)}px`;
}

function submit() {
  if (!canSend.value) return;
  emit('send', text.value, file.value);
  text.value = '';
  file.value = null;
  requestAnimationFrame(resizeInput);
}
</script>

<style scoped>
.composer {
  background: var(--ion-toolbar-background);
  border-top: 1px solid var(--relay-border);
  padding-bottom: env(safe-area-inset-bottom);
}
.bar {
  display: grid;
  grid-template-columns: 36px 1fr 36px;
  align-items: center;
  gap: 6px;
  padding: 7px 10px 8px;
}
.hidden {
  display: none;
}
.attach-button,
.send-button {
  --padding-start: 0;
  --padding-end: 0;
  --border-radius: 50%;
  width: 36px;
  height: 36px;
  margin: 0;
}
.attach-button {
  --background: var(--relay-input);
  --background-activated: rgba(142, 162, 184, 0.16);
  --color: var(--relay-muted);
  --background-hover: rgba(142, 162, 184, 0.12);
}
.attach-button ion-icon {
  font-size: 19px;
}
.send-button {
  --background: #2aabee;
  --background-activated: #177fcd;
  --background-hover: #239bdd;
  --box-shadow: none;
  --color: #ffffff;
}
.send-button[disabled] {
  --background: var(--relay-input);
  --color: var(--relay-muted);
  opacity: 1;
}
.send-button ion-icon {
  margin: 0;
  font-size: 17px;
}
.input-shell {
  display: grid;
  min-height: 36px;
  border: 1px solid var(--relay-border);
  border-radius: 18px;
  background: var(--relay-input);
  overflow: hidden;
}
textarea {
  display: block;
  width: 100%;
  min-height: 34px;
  max-height: 110px;
  margin: 0;
  padding: 7px 12px;
  border: 0;
  outline: 0;
  resize: none;
  appearance: none;
  background: transparent;
  color: var(--ion-text-color);
  font-size: 14px;
  line-height: 20px;
  caret-color: #2aabee;
  overflow-y: auto;
}
textarea::placeholder {
  color: var(--relay-muted);
  opacity: 1;
}
textarea:focus {
  outline: none;
}
</style>
