<template>
  <ion-page>
    <ion-header class="ion-no-border">
      <ion-toolbar style="--background: transparent;">
        <ion-buttons slot="end">
          <LanguageSelector />
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <div class="content-wrap auth-card">
        <h1>{{ t('auth.register.title') }}</h1>
        <p class="muted">{{ t('auth.register.subtitle') }}</p>
        <ErrorState v-if="error" :message="error" />
        <RegisterForm :loading="auth.loading" @submit="submit" />
        <ion-button fill="clear" expand="block" router-link="/login">{{ t('auth.register.existingAccount') }}</ion-button>
      </div>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { IonButton, IonContent, IonPage, IonHeader, IonToolbar, IonButtons } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import RegisterForm from '@/components/auth/RegisterForm.vue';
import LanguageSelector from '@/components/LanguageSelector.vue';
import ErrorState from '@/components/ErrorState.vue';
import { displayError } from '@/api/client';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const router = useRouter();
const error = ref('');
const { t } = useI18n();

async function submit(username: string, displayName: string, email: string, password: string) {
  error.value = '';
  try {
    await auth.register(username, displayName, email, password);
    router.replace('/conversations');
  } catch (err: unknown) {
    error.value = displayError(err, t('auth.register.failed'));
  }
}
</script>
