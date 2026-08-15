import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Used by Storybook (react-vite framework). Vitest has its own config.
export default defineConfig({ plugins: [react(), tailwindcss()] });
