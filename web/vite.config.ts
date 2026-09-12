import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// No CDN, no Google Fonts, no runtime network call -- the final rehearsal is
// wifi off. Everything the app needs ships in the build.
export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1200,
  },
});
