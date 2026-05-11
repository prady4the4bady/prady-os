/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig({
    plugins: [react()],
    server: {
        port: 3000,
        strictPort: true,
        proxy: {
            "/swarm": {
                target: "http://localhost:8004",
                changeOrigin: true,
            },
            "/models": {
                target: "http://localhost:8002",
                changeOrigin: true,
            },
            "/screen": {
                target: "http://localhost:8003",
                changeOrigin: true,
            },
            "/gateway": {
                target: "http://localhost:11430",
                changeOrigin: true,
                rewrite: function (path) { return path.replace(/^\/gateway/, ""); },
            },
        },
    },
    test: {
        environment: "jsdom",
        globals: true,
        setupFiles: ["./src/test/setup.ts"],
    },
});
