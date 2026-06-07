<template>
  <ion-page>
    <ion-content class="page-content">
      <div class="content-wrap auth-card">
        <h1>Relay</h1>
        <p class="muted">Sign in to continue.</p>
        <ErrorState v-if="error" :message="error" />
        <LoginForm :loading="auth.loading" @submit="submit" />
        <ion-button fill="clear" expand="block" router-link="/register">Create account</ion-button>
      </div>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { IonButton, IonContent, IonPage } from '@ionic/vue';
import LoginForm from '@/components/auth/LoginForm.vue';
import ErrorState from '@/components/ErrorState.vue';
import { displayError } from '@/api/client';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const router = useRouter();
const error = ref('');

async function submit(login: string, password: string) {
  error.value = '';
  try {
    await auth.login(login, password);
    router.replace('/conversations');
  } catch (err: unknown) {
    error.value = displayError(err, 'Login failed');
  }
}
</script>
