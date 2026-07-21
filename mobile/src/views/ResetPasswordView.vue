<template>
  <ion-page>
    <ion-header class="ion-no-border">
      <ion-toolbar style="--background: transparent;">
        <ion-buttons slot="start">
          <ion-back-button default-href="/login" text="" />
        </ion-buttons>
        <ion-buttons slot="end">
          <LanguageSelector />
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <div class="content-wrap auth-card">
        <h1>{{ t('auth.reset.title') }}</h1>
        <p class="muted">{{ t('auth.reset.subtitle') }}</p>
        <ErrorState v-if="error" :message="error" />
        <form @submit.prevent="submit">
          <ion-item v-if="!queryToken">
            <ion-input
              v-model="pastedToken"
              :label="t('auth.reset.tokenLabel')"
              label-placement="stacked"
              autocomplete="off"
              required
            />
          </ion-item>
          <ion-item>
            <ion-input
              v-model="password"
              :label="t('auth.reset.newPassword')"
              label-placement="stacked"
              type="password"
              autocomplete="new-password"
              :minlength="8"
              :maxlength="128"
              required
            />
          </ion-item>
          <ion-item>
            <ion-input
              v-model="confirmation"
              :label="t('auth.reset.confirmPassword')"
              label-placement="stacked"
              type="password"
              autocomplete="new-password"
              :minlength="8"
              :maxlength="128"
              required
            />
          </ion-item>
          <ion-button class="submit" expand="block" type="submit" :disabled="loading">
            {{ t('auth.reset.action') }}
          </ion-button>
        </form>
        <ion-button fill="clear" expand="block" router-link="/login">{{ t('auth.forgot.backToLogin') }}</ion-button>
      </div>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  IonBackButton,
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonInput,
  IonItem,
  IonPage,
  IonToolbar
} from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { apiFetch, displayError } from '@/api/client';
import ErrorState from '@/components/ErrorState.vue';
import LanguageSelector from '@/components/LanguageSelector.vue';
import { resetTokenFromQuery, validateNewPassword } from '@/utils/password-recovery';

const route = useRoute();
const router = useRouter();
const queryToken = resetTokenFromQuery(route.query.token);
const pastedToken = ref('');
const password = ref('');
const confirmation = ref('');
const loading = ref(false);
const error = ref('');
const { t } = useI18n();

async function submit() {
  error.value = '';
  const token = queryToken || pastedToken.value.trim();
  if (!token) {
    error.value = t('auth.reset.tokenRequired');
    return;
  }
  const validationError = validateNewPassword(password.value, confirmation.value);
  if (validationError) {
    error.value = t(`auth.reset.validation.${validationError}`);
    return;
  }

  loading.value = true;
  try {
    await apiFetch<void>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: password.value })
    });
    await router.replace({ path: '/login', query: { reset: 'success' } });
  } catch (err: unknown) {
    error.value = displayError(err, t('auth.reset.failed'));
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.submit {
  margin-top: 18px;
}
</style>
