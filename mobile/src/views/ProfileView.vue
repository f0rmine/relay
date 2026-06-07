<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-buttons slot="start"><ion-back-button default-href="/conversations" /></ion-buttons>
        <ion-title>Profile</ion-title>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <div class="profile content-wrap">
        <Avatar :name="auth.user?.display_name || 'Me'" :url="auth.user?.avatar_url" :size="96" />
        <h2>{{ auth.user?.display_name }}</h2>
        <p class="muted">@{{ auth.user?.username }}</p>
        <input ref="avatarInput" type="file" accept="image/*" hidden @change="uploadAvatar" />
        <ion-button fill="outline" :disabled="saving" @click="avatarInput?.click()">Change avatar</ion-button>
      </div>
      <ErrorState v-if="error" :message="error" />
      <ion-list class="profile-list">
        <ion-item>
          <ion-input v-model="displayName" label="Display name" label-placement="stacked" />
        </ion-item>
        <ion-item>
          <ion-input v-model="email" label="Email" label-placement="stacked" type="email" />
        </ion-item>
      </ion-list>
      <ion-button expand="block" class="action" :disabled="saving" @click="save">Save</ion-button>
      <ion-button expand="block" fill="clear" color="danger" @click="logout">Log out</ion-button>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { ref, watchEffect } from 'vue';
import { useRouter } from 'vue-router';
import { IonBackButton, IonButton, IonButtons, IonContent, IonHeader, IonInput, IonItem, IonList, IonPage, IonTitle, IonToolbar } from '@ionic/vue';
import { apiFetch, displayError } from '@/api/client';
import type { User } from '@/api/types';
import ErrorState from '@/components/ErrorState.vue';
import Avatar from '@/components/users/Avatar.vue';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const router = useRouter();
const displayName = ref('');
const email = ref('');
const avatarInput = ref<HTMLInputElement | null>(null);
const saving = ref(false);
const error = ref('');
const allowedAvatarTypes = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif']);

watchEffect(() => {
  displayName.value = auth.user?.display_name || '';
  email.value = auth.user?.email || '';
});

async function save() {
  saving.value = true;
  error.value = '';
  try {
    auth.setUser(await apiFetch<User>('/users/me/profile', {
      method: 'PATCH',
      body: JSON.stringify({ display_name: displayName.value, email: email.value })
    }));
  } catch (err: unknown) {
    error.value = displayError(err, 'Profile update failed');
  } finally {
    saving.value = false;
  }
}

async function uploadAvatar(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (!allowedAvatarTypes.has(file.type)) {
    error.value = 'Avatar upload failed: choose a JPG, PNG, WebP, or GIF image.';
    if (avatarInput.value) avatarInput.value.value = '';
    return;
  }
  saving.value = true;
  error.value = '';
  const form = new FormData();
  form.append('file', file);
  try {
    auth.setUser(await apiFetch<User>('/users/me/avatar', { method: 'POST', body: form }));
  } catch (err: unknown) {
    error.value = `Avatar upload failed: ${displayError(err, 'unknown error')}`;
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
