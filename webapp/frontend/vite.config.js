// © 2026 Martín Viera. Todos los derechos reservados.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En dev, /api se proxya al backend FastAPI (puerto 8800).
// En producción el propio backend sirve dist/, así que /api es same-origin.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8800" } },
});
