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
    <div v-if="!editingMessage && scheduledIso" class="edit-bar">
      <ion-icon :icon="timeOutline" class="edit-icon" />
      <span class="edit-label">{{ t('chat.scheduledFor', { date: scheduledLabel }) }}</span>
      <ion-button fill="clear" class="cancel-edit" @click="clearSchedule" :aria-label="t('chat.cancelSchedule')">
        <ion-icon :icon="closeOutline" />
      </ion-button>
    </div>
    <div v-if="!editingMessage && scheduleOpen" class="schedule-panel">
      <label class="schedule-label">{{ t('chat.scheduleTime') }}</label>
      <input
        v-model="scheduledLocal"
        type="datetime-local"
        class="schedule-input"
        :min="scheduleMin"
        :max="scheduleMax"
      />
      <ion-button fill="clear" size="small" @click="clearSchedule">{{ t('chat.cancel') }}</ion-button>
    </div>
    <AttachmentPreview v-if="!editingMessage" :file="file" @clear="file = null" />
    <div v-if="!editingMessage && mentionOpen && mentionMatches.length" class="mention-list" data-testid="mention-list">
      <button
        v-for="participant in mentionMatches"
        :key="participant.id"
        type="button"
        class="mention-item"
        @mousedown.prevent="selectMention(participant)"
      >
        <span class="mention-name">{{ participant.display_name }}</span>
        <span class="mention-username">@{{ participant.username }}</span>
      </button>
    </div>
    <div class="bar">
      <ion-button v-if="!editingMessage" fill="clear" class="attach-button" shape="round" @click="pick" :aria-label="t('chat.attachFile')">
        <ion-icon :icon="attachOutline" />
      </ion-button>
      <input ref="fileInput" class="hidden" type="file" accept="image/*,video/*,audio/*,application/pdf,text/plain,.doc,.docx" @change="onFile" />
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
          @input="onInput"
          @focus="onFocus"
          @blur="onBlur"
        ></textarea>
      </div>
      <ion-button
        v-if="!editingMessage"
        fill="clear"
        class="attach-button"
        shape="round"
        :class="{ active: scheduleOpen || scheduledIso }"
        @click="toggleSchedule"
        :aria-label="t('chat.schedule')"
      >
        <ion-icon :icon="timeOutline" />
      </ion-button>
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
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { IonButton, IonIcon } from '@ionic/vue';
import { attachOutline, paperPlaneOutline, closeOutline, createOutline, checkmarkOutline, micOutline, stopOutline, returnDownForwardOutline, timeOutline } from 'ionicons/icons';
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
  participants?: Array<{ id: string; display_name: string; username: string }>;
}>();
const emit = defineEmits<{
  send: [text: string, file: File | null, complete: (accepted: boolean) => void, scheduledAt?: string | null, mentions?: string[]];
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

const scheduleOpen = ref(false);
const scheduledLocal = ref('');
const mentionQuery = ref('');
const mentionStart = ref(0);
const mentionOpen = ref(false);
const mentionedIds = ref<Set<string>>(new Set());

function toLocalInput(value: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

const scheduleMin = computed(() => toLocalInput(new Date(Date.now() + 60_000)));
const scheduleMax = computed(() => toLocalInput(new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)));

const scheduledIso = computed<string | null>(() => {
  if (!scheduledLocal.value) return null;
  const date = new Date(scheduledLocal.value);
  if (Number.isNaN(date.getTime()) || date.getTime() <= Date.now()) return null;
  return date.toISOString();
});

const { t, d } = useI18n();
const scheduledLabel = computed(() => (scheduledIso.value ? d(new Date(scheduledIso.value), 'dateTime') : ''));

const mentionMatches = computed(() => {
  const query = mentionQuery.value.trim().toLowerCase();
  if (!query || !props.participants?.length) return [];
  return props.participants
    .filter(
      (p) =>
        p.display_name.toLowerCase().includes(query) ||
        p.username.toLowerCase().includes(query)
    )
    .slice(0, 6);
});

function toggleSchedule() {
  scheduleOpen.value = !scheduleOpen.value;
  if (scheduleOpen.value && !scheduledLocal.value) {
    const soon = new Date(Date.now() + 60 * 60 * 1000);
    scheduledLocal.value = toLocalInput(soon);
  }
}

function clearSchedule() {
  scheduledLocal.value = '';
  scheduleOpen.value = false;
}

function detectMention() {
  const input = textInput.value;
  if (!input || !props.participants?.length) {
    mentionOpen.value = false;
    return;
  }
  const caret = input.selectionStart ?? text.value.length;
  const before = text.value.slice(0, caret);
  const match = /@([^\s@]*)$/.exec(before);
  if (match && match[1].length >= 1) {
    mentionQuery.value = match[1];
    mentionStart.value = caret - match[0].length;
    mentionOpen.value = true;
  } else {
    mentionOpen.value = false;
  }
}

function onInput() {
  resizeInput();
  detectMention();
}

async function selectMention(participant: { id: string; display_name: string; username: string }) {
  const caret = textInput.value?.selectionStart ?? text.value.length;
  const end = mentionStart.value + 1 + mentionQuery.value.length;
  const inserted = `@${participant.display_name} `;
  text.value = text.value.slice(0, mentionStart.value) + inserted + text.value.slice(end);
  const next = new Set(mentionedIds.value);
  next.add(participant.id);
  mentionedIds.value = next;
  mentionOpen.value = false;
  resizeInput();
  await nextTick();
  const position = mentionStart.value + inserted.length;
  textInput.value?.focus();
  try {
    textInput.value?.setSelectionRange(position, position);
  } catch {
    // selection API may be unavailable
  }
}

function resolveMentions(): string[] {
  const resolved = new Set<string>(mentionedIds.value);
  for (const participant of props.participants || []) {
    if (text.value.includes(`@${participant.display_name}`)) resolved.add(participant.id);
  }
  return [...resolved];
}

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
  detectMention();
}

function onBlur() {
  typingStopTimer = setTimeout(() => {
    typingStopTimer = null;
    typingActive.value = false;
    emit('typing', false);
    mentionOpen.value = false;
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
    const mentions = resolveMentions();
    emit('send', text.value, file.value, (accepted) => {
      if (!accepted) return;
      text.value = '';
      file.value = null;
      mentionedIds.value = new Set();
      mentionOpen.value = false;
      clearSchedule();
      if (fileInput.value) fileInput.value.value = '';
      requestAnimationFrame(resizeInput);
    }, scheduledIso.value, mentions);
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
.schedule-panel {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px 0;
}
.schedule-label {
  font-size: 13px;
  color: var(--relay-muted);
}
.schedule-input {
  flex: 1;
  min-width: 0;
  padding: 6px 8px;
  border: 1px solid var(--relay-border);
  border-radius: 8px;
  background: var(--relay-input);
  color: var(--ion-text-color);
  font-size: 14px;
}
.mention-list {
  display: flex;
  flex-direction: column;
  margin: 6px 10px 0;
  border: 1px solid var(--relay-border);
  border-radius: 10px;
  background: var(--relay-panel);
  overflow: hidden;
}
.mention-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  padding: 8px 12px;
  border: none;
  background: transparent;
  color: var(--ion-text-color);
  text-align: left;
  cursor: pointer;
}
.mention-item:active {
  background: var(--relay-border);
}
.mention-name {
  font-size: 14px;
  font-weight: 600;
}
.mention-username {
  font-size: 12px;
  color: var(--relay-muted);
}
.record-timer {
  font-size: 12px;
  color: #ff8a80;
}
.bar {
  display: flex;
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
  flex-shrink: 0;
}
.attach-button {
  --background: var(--relay-input);
  --background-activated: rgba(142, 162, 184, 0.16);
  --color: var(--relay-muted);
  --background-hover: rgba(142, 162, 184, 0.12);
}
.attach-button.active {
  --color: var(--ion-color-primary);
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
  flex: 1;
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
