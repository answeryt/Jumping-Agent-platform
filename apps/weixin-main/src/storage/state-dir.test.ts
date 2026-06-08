import { describe, it, expect, vi, afterEach } from "vitest";
import os from "node:os";
import path from "node:path";
import { resolveStateDir } from "./state-dir.js";

describe("resolveStateDir", () => {
  afterEach(() => {
    delete process.env.WEIXIN_STATE_DIR;
    delete process.env.WEIXIN_ILINK_STATE_DIR;
  });

  it("returns WEIXIN_STATE_DIR when set", () => {
    process.env.WEIXIN_STATE_DIR = "/custom/state";
    expect(resolveStateDir()).toBe("/custom/state");
  });

  it("returns WEIXIN_ILINK_STATE_DIR when WEIXIN_STATE_DIR is unset", () => {
    delete process.env.WEIXIN_STATE_DIR;
    process.env.WEIXIN_ILINK_STATE_DIR = "/weixin/state";
    expect(resolveStateDir()).toBe("/weixin/state");
  });

  it("prefers WEIXIN_STATE_DIR over WEIXIN_ILINK_STATE_DIR", () => {
    process.env.WEIXIN_STATE_DIR = "/weixin";
    process.env.WEIXIN_ILINK_STATE_DIR = "/weixin-ilink";
    expect(resolveStateDir()).toBe("/weixin");
  });

  it("falls back to ~/.weixin-ilink when no env var is set", () => {
    delete process.env.WEIXIN_STATE_DIR;
    delete process.env.WEIXIN_ILINK_STATE_DIR;
    const expected = path.join(os.homedir(), ".weixin-ilink");
    expect(resolveStateDir()).toBe(expected);
  });

  it("trims whitespace from env vars", () => {
    process.env.WEIXIN_STATE_DIR = "  ";
    process.env.WEIXIN_ILINK_STATE_DIR = " /trimmed ";
    expect(resolveStateDir()).toBe("/trimmed");
  });
});
