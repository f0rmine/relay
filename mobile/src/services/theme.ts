const KEY = 'relay:theme';

export type ThemeName = 'dark' | 'light';

export function currentTheme(): ThemeName {
  try {
    return (window.localStorage.getItem(KEY) as ThemeName) || 'dark';
  } catch {
    return 'dark';
  }
}

export function applyTheme(theme: ThemeName): void {
  document.body.classList.toggle('theme-light', theme === 'light');
}

export function setTheme(theme: ThemeName): void {
  try {
    window.localStorage.setItem(KEY, theme);
  } catch {
    // ignore
  }
  applyTheme(theme);
}
