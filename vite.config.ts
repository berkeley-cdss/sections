import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the Flask backend runs on :8000 (`python3 server/main.py`).
const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    // The Dockerfile copies build/ into the Flask app's static folder.
    outDir: "build",
    // Bundles go under /static/ (as with Create React App), because /assets/
    // serves the server-rendered pages' stylesheets.
    assetsDir: "static",
  },
  server: {
    port: 3000,
    proxy: {
      // Course APIs, plus the server-rendered pages and login flow.
      "^/offerings/\\d+/api/": backend,
      "^/offerings/?$": backend,
      "/offerings/new": backend,
      "/login/": backend,
      "/authorized/": backend,
      "/logout/": backend,
      "/assets/": backend,
    },
  },
});
