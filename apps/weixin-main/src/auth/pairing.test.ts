import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

vi.mock("../util/logger.js", () => ({
  logger: {
    info: vi.fn(),
    debug: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

let tmpDir: string;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "pairing-test-"));
  process.env.WEIXIN_STATE_DIR = tmpDir;
});

afterEach(() => {
  delete process.env.WEIXIN_STATE_DIR;
  delete process.env.WEIXIN_CREDENTIALS_DIR;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

async function loadModule() {
  vi.resetModules();
  return await import("./pairing.js");
}

describe("resolveFrameworkAllowFromPath", () => {
  it("returns correct path for a given accountId", async () => {
    const { resolveFrameworkAllowFromPath } = await loadModule();
    const result = resolveFrameworkAllowFromPath("test-account");
    expect(result).toBe(
      path.join(tmpDir, "credentials", "weixin-test-account-allowFrom.json"),
    );
  });

  it("respects WEIXIN_CREDENTIALS_DIR override", async () => {
    const customDir = path.join(tmpDir, "custom-creds");
    process.env.WEIXIN_CREDENTIALS_DIR = customDir;
    const { resolveFrameworkAllowFromPath } = await loadModule();
    const result = resolveFrameworkAllowFromPath("my-bot");
    expect(result).toBe(path.join(customDir, "weixin-my-bot-allowFrom.json"));
  });

  it("sanitizes special characters in accountId", async () => {
    const { resolveFrameworkAllowFromPath } = await loadModule();
    const result = resolveFrameworkAllowFromPath("abc@im.bot");
    // Only [\\/:*?"<>|] and ".." are replaced; @ and dots are preserved
    expect(result).toContain("weixin-abc@im.bot-allowFrom.json");
  });
});

describe("registerUserInFrameworkStore", () => {
  it("creates file and adds userId when file does not exist", async () => {
    const { registerUserInFrameworkStore, resolveFrameworkAllowFromPath } =
      await loadModule();
    const result = await registerUserInFrameworkStore({
      accountId: "acc1",
      userId: "user-abc",
    });
    expect(result.changed).toBe(true);

    const filePath = resolveFrameworkAllowFromPath("acc1");
    const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    expect(content).toEqual({ version: 1, allowFrom: ["user-abc"] });
  });

  it("appends userId to existing allowFrom list", async () => {
    const { registerUserInFrameworkStore, resolveFrameworkAllowFromPath } =
      await loadModule();
    const filePath = resolveFrameworkAllowFromPath("acc2");
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(
      filePath,
      JSON.stringify({ version: 1, allowFrom: ["existing-user"] }),
      "utf-8",
    );

    const result = await registerUserInFrameworkStore({
      accountId: "acc2",
      userId: "new-user",
    });
    expect(result.changed).toBe(true);

    const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    expect(content.allowFrom).toEqual(["existing-user", "new-user"]);
  });

  it("returns changed=false when userId already exists", async () => {
    const { registerUserInFrameworkStore, resolveFrameworkAllowFromPath } =
      await loadModule();
    const filePath = resolveFrameworkAllowFromPath("acc3");
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(
      filePath,
      JSON.stringify({ version: 1, allowFrom: ["user-abc"] }),
      "utf-8",
    );

    const result = await registerUserInFrameworkStore({
      accountId: "acc3",
      userId: "user-abc",
    });
    expect(result.changed).toBe(false);

    const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    expect(content.allowFrom).toEqual(["user-abc"]);
  });

  it("returns changed=false for empty userId", async () => {
    const { registerUserInFrameworkStore } = await loadModule();
    const result = await registerUserInFrameworkStore({
      accountId: "acc4",
      userId: "  ",
    });
    expect(result.changed).toBe(false);
  });

  it("trims userId before storing", async () => {
    const { registerUserInFrameworkStore, resolveFrameworkAllowFromPath } =
      await loadModule();
    await registerUserInFrameworkStore({
      accountId: "acc5",
      userId: "  user-trimmed  ",
    });

    const filePath = resolveFrameworkAllowFromPath("acc5");
    const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    expect(content.allowFrom).toEqual(["user-trimmed"]);
  });

  it("handles corrupted file gracefully", async () => {
    const { registerUserInFrameworkStore, resolveFrameworkAllowFromPath } =
      await loadModule();
    const filePath = resolveFrameworkAllowFromPath("acc7");
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, "not-valid-json{{{", "utf-8");

    const result = await registerUserInFrameworkStore({
      accountId: "acc7",
      userId: "user-recover",
    });
    expect(result.changed).toBe(true);

    const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    expect(content.allowFrom).toEqual(["user-recover"]);
  });
});
