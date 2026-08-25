<template>
  <div class="composer">
    <div v-if="editingMessage" class="edit-bar">
      <ion-icon :icon="createOutline" class="edit-icon" />
      <span class="edit-label">{{ t('chat.editMessage') }}</span>
      <ion-button fill="clear" class="cancel-edit" @click="cancelEdit" :aria-label="t('chat.cancelEdit')">
        <ion-icon :icon="closeOutline" />
      </ion-button>
    </div>
    <AttachmentPreview v-if="!editingMessage" :file="file" @clear="file = null" />
    <div class="bar">
      <ion-button v-if="!editingMessage" fill="clear" class="attach-button" shape="round" @click="pick" :aria-label="t('chat.attachFile')">
        <ion-icon :icon="attachOutline" />
      </ion-button>
      <input ref="fileInput" class="hidden" type="file" @change="onFile" />
      <div class="input-shell">
        <textarea
          ref="textInput"
          v-model="text"
          rows="1"
          :placeholder="t('chat.messagePlaceholder')"
          autocomplete="off"
          autocapitalize="sentences"
          spellcheck="false"
          enterkeyhint="send"
          @input="resizeInput"
          @focus="onFocus"
          @blur="onBlur"
        ></textarea>
      </div>
      <ion-button class="send-button" shape="round" :disabled="!canSend || sending" @click="submit" :aria-label="editingMessage ? t('chat.editMessage') : t('chat.sendMessage')">
        <ion-icon :icon="editingMessage ? checkmarkOutline : paperPlaneOutline" />
      </ion-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { IonButton, IonIcon } from '@ionic/vue';
import { attachOutline, paperPlaneOutline, closeOutline, createOutline, checkmarkOutline } from 'ionicons/icons';
import { useI18n } from 'vue-i18n';
import AttachmentPreview from './AttachmentPreview.vue';

export interface EditingMessage {
  id: string;
  text: string;
}

const props = defineProps<{ sending?: boolean; editingMessage?: EditingMessage | null }>();
const emit = defineEmits<{
  send: [text: string, file: File | null, complete: (accepted: boolean) => void];
  typing: [active: boolean];
  edit: [text: string, complete: (accepted: boolean) => void];
  'cancel-edit': [];
}>();
const text = ref('');
const file = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const textInput = ref<HTMLTextAreaElement | null>(null);
const canSend = computed(() => text.value.trim().length > 0 || file.value);
const { t } = useI18n();

let typingStopTimer: ReturnType<typeof setTimeout> | null = null;
const typingActive = ref(false);

watch(() => props.editingMessage, (msg) => {
  if (msg) {
    text.value = msg.text;
    file.value = null;
    if (fileInput.value) fileInput.value.value = '';
    requestAnimationFrame(resizeInput);
  }
}, { immediate: true });

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

function stopTyping() {
  if (typingStopTimer) {
    clearTimeout(typingStopTimer);
    typingStopTimer = null;
  }
  if (typingActive.value) {
    typingActive.value = false;
    emit('typing', false);
  }
}

onBeforeUnmount(stopTyping);

function onFocus() {
  if (typingStopTimer) {
    clearTimeout(typingStopTimer);
    typingStopTimer = null;
  }
  if (!typingActive.value) {
    typingActive.value = true;
    emit('typing', true);
  }
}

function onBlur() {
  typingStopTimer = setTimeout(() => {
    typingStopTimer = null;
    typingActive.value = false;
    emit('typing', false);
  }, 500);
}

function cancelEdit() {
  text.value = '';
  requestAnimationFrame(resizeInput);
  emit('cancel-edit');
}

function submit() {
  if (!canSend.value) return;
  stopTyping();
  if (props.editingMessage) {
    emit('edit', text.value.trim(), (accepted) => {
      if (!accepted) return;
      text.value = '';
      requestAnimationFrame(resizeInput);
    });
  } else {
    emit('send', text.value, file.value, (accepted) => {
      if (!accepted) return;
      text.value = '';
      file.value = null;
      if (fileInput.value) fileInput.value.value = '';
      requestAnimationFrame(resizeInput);
    });
  }
}
</script>

<style scoped>
.composer {
  background: var(--ion-toolbar-background);
  border-top: 1px solid var(--relay-border);
  padding-bottom: env(safe-area-inset-bottom);
}
.edit-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px 0;
  font-size: 13px;
  color: var(--relay-muted);
}
.edit-icon {
  font-size: 14px;
  color: var(--ion-color-primary);
}
.edit-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ion-color-primary);
  font-weight: 500;
}
.cancel-edit {
  --padding-start: 0;
  --padding-end: 0;
  --color: var(--relay-muted);
  margin: 0;
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
