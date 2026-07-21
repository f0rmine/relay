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
        <h1>{{ t('auth.forgot.title') }}</h1>
        <p class="muted">{{ t('auth.forgot.subtitle') }}</p>
        <StatusState v-if="submitted" :message="t('auth.forgot.success')" />
        <ErrorState v-if="error" :message="error" />
        <form @submit.prevent="submit">
          <ion-item>
            <ion-input
              v-model="email"
              :label="t('common.email')"
              label-placement="stacked"
              type="email"
              autocomplete="email"
              required
            />
          </ion-item>
          <ion-button class="submit" expand="block" type="submit" :disabled="loading">
            {{ t('auth.forgot.action') }}
          </ion-button>
        </form>
        <ion-button fill="clear" expand="block" router-link="/login">{{ t('auth.forgot.backToLogin') }}</ion-button>
      </div>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
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
import StatusState from '@/components/StatusState.vue';

const email = ref('');
const loading = ref(false);
const submitted = ref(false);
const error = ref('');
const { t } = useI18n();

async function submit() {
  loading.value = true;
  submitted.value = false;
  error.value = '';
  try {
    await apiFetch('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email: email.value.trim() })
    });
    submitted.value = true;
  } catch (err: unknown) {
    error.value = displayError(err, t('auth.forgot.failed'));
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
