import { createTheme, type Theme } from '@mui/material/styles';
import type { PaletteMode } from '@mui/material';

// Shared, mode-independent design tokens (typography, fonts).
const typography = {
  fontFamily: "'Roboto', sans-serif",
  h1: { fontSize: '2.5rem', fontWeight: 300 },
  h2: { fontSize: '1.75rem', fontWeight: 400 },
  h3: { fontSize: '1.25rem', fontWeight: 500 },
  body1: { fontSize: '1rem' },
  button: { fontWeight: 500 },
} as const;

// Per-mode palettes. Components consume semantic tokens (background.paper,
// divider, success.main, …) so they adapt automatically to the active mode.
const lightPalette = {
  mode: 'light' as const,
  primary: { main: '#1f4788', light: '#3f67a8', dark: '#0f2748' },
  secondary: { main: '#1f7a4f', light: '#3f9a6f', dark: '#0f5a2f' },
  background: { default: '#f8f9fa', paper: '#ffffff' },
  text: { primary: '#212529', secondary: '#495057' },
  success: { main: '#006b3c', light: '#d4edda' },
  warning: { main: '#b45309', light: '#fff3cd' },
  error: { main: '#dc3545', light: '#f8d7da' },
  info: { main: '#0c5aa6', light: '#d1ecf1' },
};

const darkPalette = {
  mode: 'dark' as const,
  // Lighter blues/greens read better on dark surfaces.
  primary: { main: '#5b8dd6', light: '#82abe4', dark: '#1f4788' },
  secondary: { main: '#4fb488', light: '#7fcea8', dark: '#1f7a4f' },
  background: { default: '#121212', paper: '#1e1e1e' },
  text: { primary: '#e6e8eb', secondary: '#a0a6ad' },
  success: { main: '#3ddc84', light: '#1b3a2a' },
  warning: { main: '#f0a742', light: '#3a2f1b' },
  error: { main: '#f16b7a', light: '#3a1f23' },
  info: { main: '#4aa3e0', light: '#1b2e3a' },
};

/**
 * Build the app theme for the given color mode. `background.paper` drives the
 * AppBar/Paper/Card surfaces so both light and dark render coherently; the only
 * fixed surface is the AppBar's brand blue in light mode.
 */
export const createAppTheme = (mode: PaletteMode): Theme => {
  const palette = mode === 'dark' ? darkPalette : lightPalette;
  return createTheme({
    palette,
    typography,
    components: {
      MuiAppBar: {
        styleOverrides: {
          root: {
            // Brand blue in light mode; a deep surface in dark mode.
            backgroundColor: mode === 'dark' ? palette.background.paper : '#0f2748',
            backgroundImage: 'none',
          },
        },
      },
    },
  });
};

// Typography constants following the style guide
export const FONTS = {
  primary: "'Roboto', sans-serif",
  monospace: "'Roboto Mono', monospace",
} as const;

// Default export kept for back-compat (light theme).
const theme = createAppTheme('light');
export default theme;
