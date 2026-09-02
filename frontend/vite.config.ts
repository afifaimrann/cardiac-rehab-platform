import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: {
    rollupOptions: {
      output: {
        // Split the charting library out of the main bundle: the clinician
        // views never load it, and it is the largest single dependency.
        manualChunks: {
          react: ["react", "react-dom"],
          charts: ["recharts"],
        },
      },
    },
  },
  server: {
    port: 5173,
    // Proxy in dev so the browser talks to one origin and CORS never bites.
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
});
