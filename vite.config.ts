import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  // One three.js: addons import bare "three"; point it at the WebGPU build the game uses.
  resolve: { alias: [{ find: /^three$/, replacement: "three/webgpu" }] },
  server: { port: 5441, strictPort: true, open: false },
  preview: { port: 5440, strictPort: true, open: false },
  build: {
    target: "es2022",
    sourcemap: false,
    chunkSizeWarningLimit: 2500,
  },
});
