<template>
  <ion-page>
    <ion-content class="page-content">
      <div class="content-wrap auth-card">
        <h1>Create account</h1>
        <p class="muted">Use an email you can recover later.</p>
        <ErrorState v-if="error" :message="error" />
        <RegisterForm :loading="auth.loading" @submit="submit" />
        <ion-button fill="clear" expand="block" router-link="/login">I already have an account</ion-button>
      </div>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { IonButton, IonContent, IonPage } from '@ionic/vue';
import RegisterForm from '@/components/auth/RegisterForm.vue';
import ErrorState from '@/components/ErrorState.vue';
import { displayError } from '@/api/client';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const router = useRouter();
const error = ref('');

async function submit(username: string, displayName: string, email: string, password: string) {
  error.value = '';
  try {
    await auth.register(username, displayName, email, password);
    router.replace('/conversations');
  } catch (err: unknown) {
    error.value = displayError(err, 'Registration failed');
  }
}
</script>
