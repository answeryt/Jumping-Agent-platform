import path from "node:path";

import {
  registerWeixinAccountId,
  loadWeixinAccount,
  saveWeixinAccount,
  resolveWeixinAccount,
  clearStaleAccountsForUserId,
  DEFAULT_BASE_URL,
  normalizeAccountId,
} from "./auth/accounts.js";
import type { ResolvedWeixinAccount, WeixinRuntimeConfig } from "./auth/accounts.js";
import { notifyStop, notifyStart } from "./api/api.js";
import { assertSessionActive } from "./api/session-guard.js";
import { getContextToken, restoreContextTokens, clearContextTokensForAccount } from "./messaging/inbound.js";
import { logger } from "./util/logger.js";
import {
  DEFAULT_ILINK_BOT_TYPE,
  startWeixinLoginWithQr,
  waitForWeixinLogin,
  displayQRCode,
} from "./auth/login-qr.js";
import type { WeixinQrStartResult, WeixinQrWaitResult } from "./auth/login-qr.js";
import { applyWeixinMessageSendingHook, emitWeixinMessageSent } from "./messaging/outbound-hooks.js";
import { sendWeixinMediaFile } from "./messaging/send-media.js";
import { sendMessageWeixin, StreamingMarkdownFilter } from "./messaging/send.js";
import { monitorWeixinProvider } from "./monitor/monitor.js";
import type { MonitorWeixinOpts } from "./monitor/monitor.js";

export type WeixinLoginOptions = {
  accountId?: string;
  verbose?: boolean;
  timeoutMs?: number;
};

export type WeixinSendTextOptions = {
  cfg?: WeixinRuntimeConfig;
  to: string;
  text: string;
  accountId: string;
  contextToken?: string;
};

export type WeixinSendMediaOptions = WeixinSendTextOptions & {
  mediaPath: string;
};

export type StartWeixinAccountOptions = Omit<
  MonitorWeixinOpts,
  "baseUrl" | "cdnBaseUrl" | "token" | "accountId"
> & {
  cfg?: WeixinRuntimeConfig;
  accountId: string;
};

function ensureConfigured(account: ResolvedWeixinAccount): void {
  assertSessionActive(account.accountId);
  if (!account.configured) {
    throw new Error("weixin not configured: please complete QR login first");
  }
}

export async function loginWithQrStart(options: {
  accountId?: string;
  force?: boolean;
  verbose?: boolean;
} = {}): Promise<WeixinQrStartResult> {
  const savedBaseUrl = options.accountId ? loadWeixinAccount(options.accountId)?.baseUrl?.trim() : "";
  return startWeixinLoginWithQr({
    accountId: options.accountId,
    apiBaseUrl: savedBaseUrl || DEFAULT_BASE_URL,
    botType: DEFAULT_ILINK_BOT_TYPE,
    force: options.force,
    verbose: options.verbose,
  });
}

export async function loginWithQrWait(options: {
  sessionKey: string;
  accountId?: string;
  timeoutMs?: number;
  verbose?: boolean;
}): Promise<WeixinQrWaitResult> {
  const savedBaseUrl = options.accountId ? loadWeixinAccount(options.accountId)?.baseUrl?.trim() : "";
  const result = await waitForWeixinLogin({
    sessionKey: options.sessionKey,
    apiBaseUrl: savedBaseUrl || DEFAULT_BASE_URL,
    timeoutMs: options.timeoutMs,
    verbose: options.verbose,
    botType: DEFAULT_ILINK_BOT_TYPE,
  });

  if (result.connected && result.botToken && result.accountId) {
    const normalizedId = normalizeAccountId(result.accountId);
    saveWeixinAccount(normalizedId, {
      token: result.botToken,
      baseUrl: result.baseUrl,
      userId: result.userId,
    });
    registerWeixinAccountId(normalizedId);
    if (result.userId) {
      clearStaleAccountsForUserId(normalizedId, result.userId, clearContextTokensForAccount);
    }
  }

  return result;
}

export async function loginWithQr(options: WeixinLoginOptions = {}): Promise<WeixinQrWaitResult> {
  const startResult = await loginWithQrStart({
    accountId: options.accountId,
    verbose: options.verbose,
  });
  if (!startResult.qrcodeUrl) {
    throw new Error(startResult.message);
  }
  await displayQRCode(startResult.qrcodeUrl);
  return loginWithQrWait({
    sessionKey: startResult.sessionKey,
    accountId: options.accountId,
    timeoutMs: options.timeoutMs ?? 480_000,
    verbose: options.verbose,
  });
}

export async function startWeixinAccount(options: StartWeixinAccountOptions): Promise<void> {
  const account = resolveWeixinAccount(options.cfg, options.accountId);
  const aLog = logger.withAccount(account.accountId);
  restoreContextTokens(account.accountId);
  ensureConfigured(account);

  try {
    const resp = await notifyStart({
      baseUrl: account.baseUrl,
      token: account.token,
    });
    if (resp.ret !== undefined && resp.ret !== 0) {
      aLog.warn(`notifyStart: ret=${resp.ret} errmsg=${resp.errmsg ?? ""}`);
    }
  } catch (err) {
    aLog.warn(`notifyStart failed during startup (ignored): ${String(err)}`);
  }

  options.setStatus?.({
    accountId: account.accountId,
    running: true,
    lastEventAt: Date.now(),
  });

  await monitorWeixinProvider({
    ...options,
    baseUrl: account.baseUrl,
    cdnBaseUrl: account.cdnBaseUrl,
    token: account.token,
    accountId: account.accountId,
  });
}

export async function stopWeixinAccount(params: {
  cfg?: WeixinRuntimeConfig;
  accountId: string;
}): Promise<void> {
  const account = resolveWeixinAccount(params.cfg, params.accountId);
  if (!account.configured || !account.token?.trim()) return;
  try {
    const resp = await notifyStop({
      baseUrl: account.baseUrl,
      token: account.token,
    });
    if (resp.ret !== undefined && resp.ret !== 0) {
      logger.withAccount(account.accountId).warn(`notifyStop: ret=${resp.ret} errmsg=${resp.errmsg ?? ""}`);
    }
  } catch (err) {
    logger.withAccount(account.accountId).warn(`notifyStop failed during shutdown (ignored): ${String(err)}`);
  }
}

export async function sendWeixinText(params: WeixinSendTextOptions): Promise<{ messageId: string }> {
  const account = resolveWeixinAccount(params.cfg, params.accountId);
  ensureConfigured(account);
  const f = new StreamingMarkdownFilter();
  let text = f.feed(params.text ?? "") + f.flush();

  const sendingResult = await applyWeixinMessageSendingHook({
    to: params.to,
    text,
    accountId: account.accountId,
  });
  if (sendingResult.cancelled) {
    return { messageId: "" };
  }
  text = sendingResult.text;

  try {
    const result = await sendMessageWeixin({
      to: params.to,
      text,
      opts: {
        baseUrl: account.baseUrl,
        token: account.token,
        contextToken: params.contextToken ?? getContextToken(account.accountId, params.to),
      },
    });
    emitWeixinMessageSent({ to: params.to, content: text, success: true, accountId: account.accountId });
    return result;
  } catch (err) {
    emitWeixinMessageSent({
      to: params.to,
      content: text,
      success: false,
      error: String(err),
      accountId: account.accountId,
    });
    throw err;
  }
}

export async function sendWeixinMedia(params: WeixinSendMediaOptions): Promise<{ messageId: string }> {
  const account = resolveWeixinAccount(params.cfg, params.accountId);
  ensureConfigured(account);
  const filePath = params.mediaPath.startsWith("file://")
    ? new URL(params.mediaPath).pathname
    : path.resolve(params.mediaPath);

  const result = await sendWeixinMediaFile({
    filePath,
    to: params.to,
    text: params.text ?? "",
    opts: {
      baseUrl: account.baseUrl,
      token: account.token,
      contextToken: params.contextToken ?? getContextToken(account.accountId, params.to),
    },
    cdnBaseUrl: account.cdnBaseUrl,
  });
  emitWeixinMessageSent({
    to: params.to,
    content: params.text ?? "",
    success: true,
    accountId: account.accountId,
  });
  return result;
}
