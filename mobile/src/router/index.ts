import { createRouter, createWebHistory } from '@ionic/vue-router';
import type { RouteRecordRaw } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/conversations' },
  { path: '/login', component: () => import('@/views/LoginView.vue'), meta: { guest: true } },
  { path: '/register', component: () => import('@/views/RegisterView.vue'), meta: { guest: true } },
  { path: '/forgot-password', component: () => import('@/views/ForgotPasswordView.vue'), meta: { guest: true } },
  { path: '/reset-password', component: () => import('@/views/ResetPasswordView.vue'), meta: { guest: true } },
  { path: '/conversations', component: () => import('@/views/ConversationsView.vue'), meta: { auth: true } },
  { path: '/chat/:id', component: () => import('@/views/ChatView.vue'), meta: { auth: true } },
  { path: '/search', component: () => import('@/views/UserSearchView.vue'), meta: { auth: true } },
  { path: '/profile', component: () => import('@/views/ProfileView.vue'), meta: { auth: true } }
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  await auth.restore();
  if (to.meta.auth && !auth.isAuthenticated) return '/login';
  if (to.meta.guest && auth.isAuthenticated) return '/conversations';
});

export default router;
