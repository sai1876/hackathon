import { defineConfig } from "@playwright/test";
export default defineConfig({ testDir: "./tests", timeout: 240000, workers: 1, use: { baseURL: "http://127.0.0.1:3000", viewport: { width: 1512, height: 982 }, launchOptions: { executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", args: ["--enable-unsafe-swiftshader"] }, screenshot: "only-on-failure" } });
