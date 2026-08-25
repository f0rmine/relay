<template>
  <div class="composer">
    <div v-if="replyMessage" class="edit-bar">
      <ion-icon :icon="returnDownForwardOutline" class="edit-icon" />
      <span class="edit-label">{{ t('chat.reply') }} · {{ replyMessage.text || t('chat.imageUnavailable') }}</span>
      <ion-button fill="clear" class="cancel-edit" @click="$emit('reply-cancel')" :aria-label="t('chat.cancelEdit')">
        <ion-icon :icon="closeOutline" />
      </ion-button>
    </div>
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
          @keydown.enter.exact.prevent="submit"
          enterkeyhint="send"
          @input="resizeInput"
          @focus="onFocus"
          @blur="onBlur"
        ></textarea>
      </div>
      <ion-button
        v-if="!editingMessage && !canSend && !recording"
        fill="clear"
        shape="round"
        class="attach-button"
        @click="toggleRecording"
        :aria-label="t('chat.recordVoice')"
      >
        <ion-icon :icon="micOutline" :color="recording ? 'danger' : undefined" />
      </ion-button>
      <span v-if="recording" class="record-timer">{{ recordSeconds }}s</span>
      <ion-button class="send-button" shape="round" :disabled="(!canSend && !recording) || sending" @click="submit" :aria-label="editingMessage ? t('chat.editMessage') : t('chat.sendMessage')">
        <ion-icon :icon="recording ? stopOutline : editingMessage ? checkmarkOutline : paperPlaneOutline" />
      </ion-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { IonButton, IonIcon } from '@ionic/vue';
import { attachOutline, paperPlaneOutline, closeOutline, createOutline, checkmarkOutline, micOutline, stopOutline, returnDownForwardOutline } from 'ionicons/icons';
import { useI18n } from 'vue-i18n';
import AttachmentPreview from './AttachmentPreview.vue';

export interface EditingMessage {
  id: string;
  text: string;
}

const props = defineProps<{
  sending?: boolean;
  editingMessage?: EditingMessage | null;
  replyMessage?: import('@/api/types').Message | null;
  initialValue?: string;
}>();
const emit = defineEmits<{
  send: [text: string, file: File | null, complete: (accepted: boolean) => void];
  typing: [active: boolean];
  edit: [text: string, complete: (accepted: boolean) => void];
  'cancel-edit': [];
  'reply-cancel': [];
  draft: [text: string];
}>();
const text = ref(props.initialValue || '');
const file = ref<File | null>(null);
const recording = ref(false);
const recordSeconds = ref(0);
let mediaRecorder: MediaRecorder | null = null;
let recordedChunks: BlobPart[] = [];
let recordStream: MediaStream | null = null;
let recordTimer: number | null = null;

watch(
  () => props.initialValue,
  (value) => {
    if (typeof value === 'string') {
      text.value = value;
      requestAnimationFrame(resizeInput);
    }
  }
);

watch(text, (value) => emit('draft', value));

async function toggleRecording() {
  if (recording.value) {
    mediaRecorder?.stop();
    return;
  }
  try {
    recordStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordedChunks = [];
    const mimeCandidates = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm'];
    const mimeType = mimeCandidates.find((candidate) => MediaRecorder.isTypeSupported(candidate));
    mediaRecorder = new MediaRecorder(recordStream, mimeType ? { mimeType } : undefined);
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size) recordedChunks.push(event.data);
    };
    mediaRecorder.onstop = finishRecording;
    mediaRecorder.start();
    recording.value = true;
    recordSeconds.value = 0;
    recordTimer = window.setInterval(() => {
      recordSeconds.value += 1;
    }, 1000);
  } catch {
    // microphone unavailable or permission denied
  }
}

function finishRecording() {
  if (recordTimer !== null) {
    window.clearInterval(recordTimer);
    recordTimer = null;
  }
  recordStream?.getTracks().forEach((track) => track.stop());
  recordStream = null;
  recording.value = false;
  if (!recordedChunks.length) return;
  const type = mediaRecorder?.mimeType || 'audio/webm';
  const extension = type.includes('mp4') ? 'm4a' : 'webm';
  const voiceFile = new File(recordedChunks, `voice-${Date.now()}.${extension}`, { type });
  file.value = voiceFile;
  submit();
}
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

onBeforeUnmount(() => {
  stopTyping();
  if (recording.value) mediaRecorder?.stop();
});

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
    if (recording.value) {
      mediaRecorder?.stop();
      return;
    }
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
.record-timer {
  font-size: 12px;
  color: #ff8a80;
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
