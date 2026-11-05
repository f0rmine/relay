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

      <h3 class="section">{{ t('profile.blocked.title') }}</h3>
      <ErrorState v-if="blockedError" :message="blockedError" />
      <ion-list v-if="blocks.blocked.length" class="profile-list">
        <ion-item v-for="user in blocks.blocked" :key="user.id">
          <Avatar slot="start" :name="user.display_name" :url="user.avatar_url" :size="34" />
          <ion-label>
            <h3>{{ user.display_name }}</h3>
            <p>@{{ user.username }}</p>
          </ion-label>
          <ion-button
            slot="end"
            fill="clear"
            color="danger"
            size="small"
            :disabled="unblockingId === user.id"
            @click="unblock(user.id)"
          >
            {{ t('profile.blocked.unblock') }}
          </ion-button>
        </ion-item>
      </ion-list>
      <p v-else class="muted hint">{{ t('profile.blocked.empty') }}</p>

      <h3 class="section">{{ t('profile.twoFactor.title') }}</h3>
      <ErrorState v-if="twoFactorError" :message="twoFactorError" />
      <ion-list class="profile-list">
        <ion-item>
          <ion-label>
            <h3>{{ twoFactorEnabled ? t('profile.twoFactor.enabled') : t('profile.twoFactor.disabled') }}</h3>
          </ion-label>
        </ion-item>
      </ion-list>

      <template v-if="twoFactorEnabled && !recoveryCodes">
        <ion-button expand="block" class="action" :disabled="twoFactorBusy" @click="disableVisible = !disableVisible">
          {{ t('profile.twoFactor.disable') }}
        </ion-button>
        <div v-if="disableVisible">
          <p class="muted hint">{{ t('profile.twoFactor.disableHint') }}</p>
          <ion-list class="profile-list">
            <ion-item>
              <ion-input v-model="disableCode" :label="t('profile.twoFactor.codeLabel')" label-placement="stacked" autocomplete="one-time-code" />
            </ion-item>
          </ion-list>
          <ion-button
            expand="block"
            class="action"
            color="danger"
            :disabled="twoFactorBusy || !disableCode.trim()"
            @click="disableTwoFactor"
          >
            {{ t('profile.twoFactor.disableAction') }}
          </ion-button>
        </div>
      </template>

      <template v-if="!twoFactorEnabled && !setupSecret && !recoveryCodes">
        <ion-button expand="block" class="action" :disabled="twoFactorBusy" @click="startTwoFactorSetup">
          {{ t('profile.twoFactor.enable') }}
        </ion-button>
      </template>

      <template v-if="setupSecret && !recoveryCodes">
        <p class="muted hint">{{ t('profile.twoFactor.setupHint') }}</p>
        <div v-if="qrCodeDataUrl" class="qr-wrap">
          <img :src="qrCodeDataUrl" alt="TOTP QR code" class="qr-code" />
        </div>
        <ion-list class="profile-list">
          <ion-item>
            <ion-label>
              <h3>{{ t('profile.twoFactor.secretLabel') }}</h3>
              <p class="secret">{{ setupSecret }}</p>
            </ion-label>
          </ion-item>
        </ion-list>
        <ion-list class="profile-list">
          <ion-item>
            <ion-input v-model="setupCode" :label="t('profile.twoFactor.codeLabel')" label-placement="stacked" inputmode="numeric" autocomplete="one-time-code" />
          </ion-item>
        </ion-list>
        <ion-button
          expand="block"
          class="action"
          :disabled="twoFactorBusy || !setupCode.trim()"
          @click="enableTwoFactor"
        >
          {{ t('profile.twoFactor.enableAction') }}
        </ion-button>
        <ion-button expand="block" fill="clear" @click="cancelSetup">{{ t('profile.twoFactor.cancel') }}</ion-button>
      </template>

      <template v-if="recoveryCodes">
        <p class="muted hint">{{ t('profile.twoFactor.recoveryTitle') }}</p>
        <p class="muted hint warning">{{ t('profile.twoFactor.recoveryWarning') }}</p>
        <ion-list class="profile-list">
          <ion-item v-for="code in recoveryCodes" :key="code">
            <ion-label>{{ code }}</ion-label>
          </ion-item>
        </ion-list>
        <ion-button expand="block" class="action" :disabled="twoFactorBusy" @click="copyRecoveryCodes">
          {{ copied ? t('profile.twoFactor.copied') : t('profile.twoFactor.copy') }}
        </ion-button>
        <ion-button expand="block" fill="clear" @click="finishRecovery">{{ t('profile.twoFactor.done') }}</ion-button>
      </template>

      <h3 class="section danger-title">{{ t('profile.deleteAccount.title') }}</h3>
      <ErrorState v-if="deleteError" :message="deleteError" />
      <p class="muted hint">{{ t('profile.deleteAccount.warning') }}</p>
      <ion-button
        v-if="!deleteConfirmVisible"
        expand="block"
        class="action"
        fill="outline"
        color="danger"
        :disabled="deleting"
        @click="deleteConfirmVisible = true"
      >
        {{ t('profile.deleteAccount.button') }}
      </ion-button>
      <div v-if="deleteConfirmVisible">
        <ion-list class="profile-list">
          <ion-item>
            <ion-input v-model="deleteConfirmInput" :label="t('profile.deleteAccount.prompt')" label-placement="stacked" autocomplete="off" />
          </ion-item>
        </ion-list>
        <ion-button
          expand="block"
          class="action"
          color="danger"
          :disabled="deleting || deleteConfirmInput !== 'DELETE'"
          @click="deleteAccount"
        >
          {{ t('profile.deleteAccount.confirm') }}
        </ion-button>
        <ion-button expand="block" fill="clear" :disabled="deleting" @click="deleteConfirmVisible = false; deleteConfirmInput = ''">
          {{ t('profile.deleteAccount.cancel') }}
        </ion-button>
      </div>

      <ion-button expand="block" fill="clear" color="danger" @click="logout">{{ t('profile.logout') }}</ion-button>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { IonBackButton, IonButton, IonButtons, IonContent, IonHeader, IonInput, IonItem, IonLabel, IonList, IonPage, IonTitle, IonToggle, IonToolbar } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import QRCode from 'qrcode';
import { apiFetch, displayError } from '@/api/client';
import type { SessionInfo, TotpSetupResponse, TwoFactorEnableResponse, User } from '@/api/types';
import ErrorState from '@/components/ErrorState.vue';
import Avatar from '@/components/users/Avatar.vue';
import LanguageSelector from '@/components/LanguageSelector.vue';
import { useAuthStore } from '@/stores/auth';
import { useBlocksStore } from '@/stores/blocks';
import { applyTheme, currentTheme, setTheme, type ThemeName } from '@/services/theme';
import { decodeJwtPayload } from '@/services/jwt';

const auth = useAuthStore();
const blocks = useBlocksStore();
const router = useRouter();
const displayName = ref('');
const email = ref('');
const avatarInput = ref<HTMLInputElement | null>(null);
const saving = ref(false);
const error = ref('');
const allowedAvatarTypes = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif']);
const { t } = useI18n();

const twoFactorEnabled = computed(() => Boolean(auth.user?.totp_enabled));
const twoFactorBusy = ref(false);
const twoFactorError = ref('');
const setupSecret = ref<string | null>(null);
const qrCodeDataUrl = ref<string | null>(null);
const setupCode = ref('');
const recoveryCodes = ref<string[] | null>(null);
const disableVisible = ref(false);
const disableCode = ref('');
const copied = ref(false);

const deleteConfirmVisible = ref(false);
const deleteConfirmInput = ref('');
const deleteError = ref('');
const deleting = ref(false);

const blockedError = ref('');
const unblockingId = ref<string | null>(null);

async function loadBlocked() {
  blockedError.value = '';
  try {
    await blocks.fetchBlocked();
  } catch (err: unknown) {
    blockedError.value = displayError(err, t('profile.blocked.loadFailed'));
  }
}

async function unblock(userId: string) {
  unblockingId.value = userId;
  blockedError.value = '';
  try {
    await blocks.unblock(userId);
  } catch (err: unknown) {
    blockedError.value = displayError(err, t('profile.blocked.unblockFailed'));
  } finally {
    unblockingId.value = null;
  }
}

onMounted(() => {
  displayName.value = auth.user?.display_name || '';
  email.value = auth.user?.email || '';
  void refreshMe();
  void loadBlocked();
});

async function refreshMe() {
  try {
    const me = await apiFetch<User>('/auth/me');
    await auth.setUser({ ...me, totp_enabled: me.totp_enabled ?? auth.user?.totp_enabled });
    displayName.value = me.display_name || displayName.value;
    email.value = me.email || email.value;
  } catch {
    // Keep the cached user when the backend is unreachable or 2FA fields are absent.
  }
}

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
    await auth.setUser({ ...updated, totp_enabled: updated.totp_enabled ?? auth.user?.totp_enabled });
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

async function startTwoFactorSetup() {
  twoFactorBusy.value = true;
  twoFactorError.value = '';
  try {
    const response = await apiFetch<TotpSetupResponse>('/auth/2fa/setup', { method: 'POST' });
    setupSecret.value = response.secret;
    setupCode.value = '';
    recoveryCodes.value = null;
    try {
      qrCodeDataUrl.value = await QRCode.toDataURL(response.otpauth_url);
    } catch {
      qrCodeDataUrl.value = null;
    }
  } catch (err: unknown) {
    twoFactorError.value = displayError(err, t('profile.twoFactor.setupFailed'));
  } finally {
    twoFactorBusy.value = false;
  }
}

function cancelSetup() {
  setupSecret.value = null;
  setupCode.value = '';
  qrCodeDataUrl.value = null;
}

async function enableTwoFactor() {
  if (!setupCode.value.trim()) return;
  twoFactorBusy.value = true;
  twoFactorError.value = '';
  try {
    const response = await apiFetch<TwoFactorEnableResponse>('/auth/2fa/enable', {
      method: 'POST',
      body: JSON.stringify({ code: setupCode.value.trim() })
    });
    recoveryCodes.value = response.recovery_codes;
    copied.value = false;
    if (auth.user) {
      await auth.setUser({ ...auth.user, totp_enabled: true });
    }
  } catch (err: unknown) {
    twoFactorError.value = displayError(err, t('profile.twoFactor.enableFailed'));
  } finally {
    twoFactorBusy.value = false;
  }
}

async function disableTwoFactor() {
  if (!disableCode.value.trim()) return;
  twoFactorBusy.value = true;
  twoFactorError.value = '';
  try {
    const value = disableCode.value.trim();
    // Backend verifies `code` as TOTP only and `recovery_code` as a recovery
    // code; route 6-digit input to `code` and anything else to `recovery_code`.
    const body = /^\d{6}$/.test(value) ? { code: value } : { recovery_code: value };
    await apiFetch<void>('/auth/2fa/disable', {
      method: 'POST',
      body: JSON.stringify(body)
    });
    if (auth.user) {
      await auth.setUser({ ...auth.user, totp_enabled: false });
    }
    disableCode.value = '';
    disableVisible.value = false;
  } catch (err: unknown) {
    twoFactorError.value = displayError(err, t('profile.twoFactor.disableFailed'));
  } finally {
    twoFactorBusy.value = false;
  }
}

async function copyRecoveryCodes() {
  if (!recoveryCodes.value?.length) return;
  try {
    const { Clipboard } = await import('@capacitor/clipboard');
    await Clipboard.write({ string: recoveryCodes.value.join('\n') });
    copied.value = true;
  } catch (err: unknown) {
    twoFactorError.value = displayError(err, t('profile.twoFactor.copyFailed'));
  }
}

function finishRecovery() {
  recoveryCodes.value = null;
  setupSecret.value = null;
  setupCode.value = '';
  qrCodeDataUrl.value = null;
  copied.value = false;
}

async function deleteAccount() {
  if (deleteConfirmInput.value !== 'DELETE') return;
  deleting.value = true;
  deleteError.value = '';
  try {
    await apiFetch<void>('/users/me', {
      method: 'DELETE',
      body: JSON.stringify({ confirmation: 'DELETE' })
    });
    await auth.logout();
    router.replace('/login');
  } catch (err: unknown) {
    deleteError.value = displayError(err, t('profile.deleteAccount.failed'));
  } finally {
    deleting.value = false;
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
.section {
  margin: 24px 16px 4px;
}
.danger-title {
  color: var(--ion-color-danger);
}
.hint {
  margin: 8px 16px;
}
.warning {
  color: var(--ion-color-warning);
}
.qr-wrap {
  display: grid;
  justify-items: center;
  margin: 8px 16px;
}
.qr-code {
  width: 200px;
  height: 200px;
  border-radius: 8px;
  background: #fff;
}
.secret {
  font-family: monospace;
  word-break: break-all;
}
.section-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 16px;
}
</style>
