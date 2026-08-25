<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-buttons slot="start"><ion-back-button default-href="/conversations" text="" /></ion-buttons>
        <ion-title>{{ t('profile.title') }}</ion-title>
        <ion-buttons slot="end">
          <LanguageSelector icon-only />
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <div class="profile content-wrap">
        <Avatar :name="auth.user?.display_name || t('common.me')" :url="auth.user?.avatar_url" :size="96" />
        <h2>{{ auth.user?.display_name }}</h2>
        <p class="muted">@{{ auth.user?.username }}</p>
        <input ref="avatarInput" type="file" accept="image/*" hidden @change="uploadAvatar" />
        <ion-button fill="outline" :disabled="saving" @click="avatarInput?.click()">{{ t('profile.changeAvatar') }}</ion-button>
      </div>
      <ErrorState v-if="error" :message="error" />
      <ion-list class="profile-list">
        <ion-item>
          <ion-input v-model="displayName" :label="t('common.displayName')" label-placement="stacked" />
        </ion-item>
        <ion-item>
          <ion-input v-model="email" :label="t('common.email')" label-placement="stacked" type="email" />
        </ion-item>
      </ion-list>
      <ion-button expand="block" class="action" :disabled="saving" @click="save">{{ t('profile.save') }}</ion-button>

      <div class="section-row">
        <span>{{ t('profile.theme') }}</span>
        <ion-toggle :checked="theme === 'light'" @ionChange="toggleTheme" />
      </div>

      <h3 class="section">{{ t('sessions.title') }}</h3>
      <ErrorState v-if="sessionsError" :message="sessionsError" />
      <ion-list class="profile-list">
        <ion-item v-for="session in sessions" :key="session.short_id">
          <ion-label>
            <h3>{{ session.current ? t('sessions.current') : session.short_id }}</h3>
            <p>{{ new Date(session.created_at).toLocaleDateString() }}</p>
          </ion-label>
          <ion-button
            v-if="!session.current"
            slot="end"
            fill="clear"
            color="danger"
            size="small"
            @click="revokeSession(session)"
          >
            {{ t('sessions.revoke') }}
          </ion-button>
        </ion-item>
      </ion-list>

      <ion-button expand="block" fill="clear" color="danger" @click="logout">{{ t('profile.logout') }}</ion-button>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { IonBackButton, IonButton, IonButtons, IonContent, IonHeader, IonInput, IonItem, IonLabel, IonList, IonPage, IonTitle, IonToggle, IonToolbar } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { apiFetch, displayError } from '@/api/client';
import type { User } from '@/api/types';
import ErrorState from '@/components/ErrorState.vue';
import Avatar from '@/components/users/Avatar.vue';
import LanguageSelector from '@/components/LanguageSelector.vue';
import type { SessionInfo } from '@/api/types';
import { useAuthStore } from '@/stores/auth';
import { applyTheme, currentTheme, setTheme, type ThemeName } from '@/services/theme';
import { decodeJwtPayload } from '@/services/jwt';

const auth = useAuthStore();
const router = useRouter();
const displayName = ref('');
const email = ref('');
const avatarInput = ref<HTMLInputElement | null>(null);
const saving = ref(false);
const error = ref('');
const allowedAvatarTypes = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif']);
const { t } = useI18n();

onMounted(() => {
  displayName.value = auth.user?.display_name || '';
  email.value = auth.user?.email || '';
});

const theme = ref<ThemeName>(currentTheme());
const sessions = ref<SessionInfo[]>([]);
const sessionsError = ref('');

function toggleTheme() {
  theme.value = theme.value === 'light' ? 'dark' : 'light';
  setTheme(theme.value);
}

async function loadSessions() {
  if (!auth.refreshToken) return;
  try {
    const payload = decodeJwtPayload(auth.refreshToken);
    const jti = typeof payload.jti === 'string' ? payload.jti : undefined;
    sessions.value = await apiFetch<SessionInfo[]>(
      `/auth/sessions${jti ? `?current_jti=${encodeURIComponent(jti)}` : ''}`
    );
  } catch {
    sessions.value = [];
  }
}

async function revokeSession(session: SessionInfo) {
  if (!session.jti) return;
  sessionsError.value = '';
  try {
    await apiFetch(`/auth/sessions/${session.jti}`, { method: 'DELETE' });
    sessions.value = sessions.value.filter((entry) => entry.jti !== session.jti);
  } catch (err: unknown) {
    sessionsError.value = displayError(err, t('sessions.revokeFailed'));
  }
}

void loadSessions();

async function save() {
  saving.value = true;
  error.value = '';
  try {
    const updated = await apiFetch<User>('/users/me/profile', {
      method: 'PATCH',
      body: JSON.stringify({ display_name: displayName.value, email: email.value })
    });
    await auth.setUser(updated);
    displayName.value = updated.display_name || '';
    email.value = updated.email || '';
  } catch (err: unknown) {
    error.value = displayError(err, t('profile.updateFailed'));
  } finally {
    saving.value = false;
  }
}

async function uploadAvatar(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (!allowedAvatarTypes.has(file.type)) {
    error.value = t('profile.avatarTypeFailed');
    if (avatarInput.value) avatarInput.value.value = '';
    return;
  }
  saving.value = true;
  error.value = '';
  const form = new FormData();
  form.append('file', file);
  try {
    await auth.setUser(await apiFetch<User>('/users/me/avatar', { method: 'POST', body: form }));
  } catch (err: unknown) {
    error.value = t('profile.avatarUploadFailed', { error: displayError(err, t('profile.unknownError')) });
  } finally {
    saving.value = false;
    if (avatarInput.value) avatarInput.value.value = '';
  }
}

async function logout() {
  await auth.logout();
  router.replace('/login');
}
</script>

<style scoped>
.profile {
  display: grid;
  justify-items: center;
  gap: 8px;
  padding: 32px 16px 20px;
}
.profile h2,
.profile p {
  margin: 0;
}
.action {
  margin: 16px;
}
.profile-list {
  margin: 8px 12px 0;
  border: 1px solid var(--relay-border);
  border-radius: 8px;
  overflow: hidden;
}
</style>
