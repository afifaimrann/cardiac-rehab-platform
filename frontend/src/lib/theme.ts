/** Theme preference, persisted per browser. */
export type Theme = "light" | "dark";

const KEY = "cr.theme";

export function storedTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch { /* private mode or blocked storage */ }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", theme === "dark" ? "#161513" : "#faf8f5");
  try {
    localStorage.setItem(KEY, theme);
  } catch { /* not fatal: the theme still applies for this session */ }
}
