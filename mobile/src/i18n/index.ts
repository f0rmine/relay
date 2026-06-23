import { createI18n } from 'vue-i18n';
import { messages } from './messages';

export type SupportedLocale = keyof typeof messages;

const LOCALE_STORAGE_KEY = 'relay.locale';
const supportedLocales: SupportedLocale[] = ['en', 'uk'];

export function isSupportedLocale(value: unknown): value is SupportedLocale {
  return typeof value === 'string' && supportedLocales.includes(value as SupportedLocale);
}

function storedLocale(): SupportedLocale | null {
  try {
    const value = localStorage.getItem(LOCALE_STORAGE_KEY);
    return isSupportedLocale(value) ? value : null;
  } catch {
    return null;
  }
}

function deviceLocale(): SupportedLocale {
  const locales = navigator.languages?.length ? navigator.languages : [navigator.language];
  return locales.some((locale) => locale.toLowerCase().split(/[-_]/)[0] === 'uk') ? 'uk' : 'en';
}

const initialLocale = storedLocale() || deviceLocale();

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale,
  fallbackLocale: 'en',
  messages,
  datetimeFormats: {
    en: {
      time: { hour: '2-digit', minute: '2-digit' },
      dateTime: { dateStyle: 'medium', timeStyle: 'short' }
    },
    uk: {
      time: { hour: '2-digit', minute: '2-digit' },
      dateTime: { dateStyle: 'medium', timeStyle: 'short' }
    }
  }
});

export function setLocale(locale: SupportedLocale): void {
  i18n.global.locale.value = locale;
  document.documentElement.lang = locale;
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // The selected locale still applies for this session when storage is unavailable.
  }
  window.dispatchEvent(new CustomEvent('relay:locale-changed', { detail: { locale } }));
}

export function currentLocale(): SupportedLocale {
  return i18n.global.locale.value;
}

export function translate(key: string, named?: Record<string, unknown>): string {
  return String(named ? i18n.global.t(key, named) : i18n.global.t(key));
}

document.documentElement.lang = initialLocale;
