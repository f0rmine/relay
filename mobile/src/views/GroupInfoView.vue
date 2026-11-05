<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-buttons slot="start">
          <ion-back-button default-href="/conversations" text="" />
        </ion-buttons>
        <ion-title>{{ t('groups.info') }}</ion-title>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <ErrorState v-if="error" :message="error" />
      <div class="wrap">
        <Avatar :name="conversation?.title || t('conversations.groupChat')" :url="conversation?.avatar_url" :size="72" />
        <h2>{{ conversation?.title }}</h2>
        <p class="muted">{{ membersLabel }}</p>
        <input ref="avatarInput" type="file" accept="image/*" hidden @change="uploadAvatar" />
        <ion-button v-if="isAdmin" fill="outline" :disabled="uploadingAvatar" @click="avatarInput?.click()">
          {{ t('groups.changeAvatar') }}
        </ion-button>
      </div>

      <ion-list v-if="isAdmin">
        <ion-item>
          <ion-input
            v-model="titleDraft"
            :label="t('groups.name')"
            label-placement="stacked"
          />
        </ion-item>
        <ion-button expand="block" class="action" :disabled="saving || titleDraft.trim() === conversation?.title" @click="saveTitle">
          {{ t('profile.save') }}
        </ion-button>
      </ion-list>

      <h3 class="section">{{ t('groups.members') }}</h3>
      <ion-list>
        <ion-item v-for="user in conversation?.participants" :key="user.id">
          <Avatar slot="start" :name="user.display_name" :url="user.avatar_url" :size="34" />
          <ion-label>
            <h3>{{ user.display_name }} <span v-if="adminIds.has(user.id)">👑</span></h3>
            <p>@{{ user.username }}</p>
          </ion-label>
          <ion-button
            v-if="isAdmin && user.id !== me"
            slot="end"
            fill="clear"
            color="danger"
            size="small"
            @click="kick(user.id)"
          >
            {{ t('groups.remove') }}
          </ion-button>
        </ion-item>
      </ion-list>

      <div v-if="isAdmin" class="add-section">
        <h3 class="section">{{ t('groups.addMembers') }}</h3>
        <UserSearchList @toggle="addMember" />
      </div>

      <div class="export-section">
        <ion-button expand="block" fill="outline" :disabled="exporting" @click="startExport">
          {{ exporting ? t('chat.exportingChat') : t('chat.exportChat') }}
        </ion-button>
        <p v-if="exportStatus" class="muted export-status">{{ exportStatus }}</p>
      </div>

      <ion-button v-if="isMember" expand="block" fill="clear" color="danger" class="leave" @click="leave">
        {{ t('groups.leave') }}
      </ion-button>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  IonBackButton,
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonInput,
  IonItem,
  IonLabel,
  IonList,
  IonPage,
  IonTitle,
  IonToolbar
} from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { apiBlob, apiFetch, displayError } from '@/api/client';
import type { Conversation, User } from '@/api/types';
import Avatar from '@/components/users/Avatar.vue';
import ErrorState from '@/components/ErrorState.vue';
import UserSearchList from '@/components/users/UserSearchList.vue';
import { useAuthStore } from '@/stores/auth';
import { useConversationsStore } from '@/stores/conversations';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const conversations = useConversationsStore();
const { t } = useI18n();
const conversationId = String(route.params.id);
const error = ref('');
const saving = ref(false);
const uploadingAvatar = ref(false);
const avatarInput = ref<HTMLInputElement | null>(null);
const titleDraft = ref('');
const exporting = ref(false);
const exportStatus = ref('');
let exportPollTimer: number | null = null;

function stopExportPoll() {
  if (exportPollTimer) window.clearInterval(exportPollTimer);
  exportPollTimer = null;
}

onUnmounted(stopExportPoll);

const conversation = computed(() => conversations.items.find((item) => item.id === conversationId));
const isAdmin = computed(() => Boolean(conversation.value?.is_admin));
const isMember = computed(() => Boolean(conversation.value));
const me = computed(() => auth.user?.id || '');
const adminIds = computed(() => new Set(conversation.value?.admin_ids || []));
const membersLabel = computed(
  () => `${conversation.value?.participants?.length || 0} ${t('groups.members')}`
);

async function refresh() {
  try {
    const fresh = await apiFetch<Conversation>(`/conversations/${conversationId}`);
    conversations.applyConversationInfo(fresh);
    if (!titleDraft.value) titleDraft.value = fresh.title || '';
  } catch (err: unknown) {
    error.value = displayError(err, t('chat.loadFailed'));
  }
}

onMounted(() => {
  void refresh();
});

async function saveTitle() {
  saving.value = true;
  error.value = '';
  try {
    const updated = await apiFetch<Conversation>(`/conversations/${conversationId}`, {
      method: 'PATCH',
      body: JSON.stringify({ title: titleDraft.value.trim() })
    });
    conversations.applyConversationInfo(updated);
  } catch (err: unknown) {
    error.value = displayError(err, t('groups.updateFailed'));
  } finally {
    saving.value = false;
  }
}

const allowedAvatarTypes = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif']);

async function uploadAvatar(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (!allowedAvatarTypes.has(file.type)) {
    error.value = t('groups.avatarTypeFailed');
    if (avatarInput.value) avatarInput.value.value = '';
    return;
  }
  uploadingAvatar.value = true;
  error.value = '';
  const form = new FormData();
  form.append('file', file);
  try {
    const updated = await apiFetch<Conversation>(`/conversations/${conversationId}/avatar`, {
      method: 'PUT',
      body: form
    });
    conversations.applyConversationInfo(updated);
  } catch (err: unknown) {
    error.value = t('groups.avatarUploadFailed', {
      error: displayError(err, t('profile.unknownError'))
    });
  } finally {
    uploadingAvatar.value = false;
    if (avatarInput.value) avatarInput.value.value = '';
  }
}

async function addMember(user: User) {
  error.value = '';
  try {
    const updated = await apiFetch<Conversation>(`/conversations/${conversationId}/participants`, {
      method: 'POST',
      body: JSON.stringify({ participant_ids: [user.id] })
    });
    conversations.applyConversationInfo(updated);
  } catch (err: unknown) {
    error.value = displayError(err, t('groups.updateFailed'));
  }
}

async function kick(userId: string) {
  error.value = '';
  try {
    await apiFetch(`/conversations/${conversationId}/participants/${userId}`, { method: 'DELETE' });
    await refresh();
  } catch (err: unknown) {
    error.value = displayError(err, t('groups.updateFailed'));
  }
}

async function leave() {
  error.value = '';
  try {
    await apiFetch(`/conversations/${conversationId}/leave`, { method: 'POST' });
    conversations.removeLocal(conversationId);
    void router.replace('/conversations');
  } catch (err: unknown) {
    error.value = displayError(err, t('groups.leaveFailed'));
  }
}

async function downloadExport(downloadUrl: string | undefined, jobId: string) {
  const blob = await apiBlob(`/exports/${jobId}/download`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `chat-export-${conversationId}.zip`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

async function startExport() {
  if (exporting.value) return;
  exporting.value = true;
  exportStatus.value = t('chat.exportingChat');
  error.value = '';
  try {
    const created = await apiFetch<{ id: string }>(`/exports`, {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId })
    });
    const jobId = created.id;
    exportPollTimer = window.setInterval(async () => {
      try {
        const status = await apiFetch<{ status: string }>(`/exports/${jobId}`);
        if (status.status === 'done' || status.status === 'completed' || status.status === 'complete') {
          stopExportPoll();
          await downloadExport(undefined, jobId);
          exportStatus.value = t('chat.exportReady');
          exporting.value = false;
        } else if (status.status === 'failed' || status.status === 'error') {
          stopExportPoll();
          exportStatus.value = t('chat.exportFailed');
          exporting.value = false;
        }
      } catch {
        stopExportPoll();
        exportStatus.value = t('chat.exportFailed');
        exporting.value = false;
      }
    }, 2000);
  } catch (err: unknown) {
    exportStatus.value = displayError(err, t('chat.exportFailed'));
    exporting.value = false;
  }
}
</script>

<style scoped>
.wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 16px 12px 6px;
}
.muted {
  color: var(--relay-muted);
}
.section {
  margin: 14px 16px 4px;
  font-size: 13px;
  color: var(--relay-muted);
}
.add-section {
  margin-top: 8px;
}
.action,
.leave {
  margin-top: 8px;
}
.export-section {
  margin: 12px 16px 0;
}
.export-status {
  margin: 6px 2px 0;
  font-size: 13px;
}
</style>
