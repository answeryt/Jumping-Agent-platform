import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { URL } from "node:url";

import {
  clearWeixinAccount,
  listWeixinAccountIds,
  loginWithQrStart,
  loginWithQrWait,
  resolveWeixinAccount,
  startWeixinAccount,
  stopWeixinAccount,
  unregisterWeixinAccountId,
} from "../../index.js";
import type { ProcessedWeixinMessage } from "../messaging/process-message.js";
import { resolveStateDir } from "../storage/state-dir.js";

type JsonRecord = Record<string, unknown>;

type LoginState = {
  sessionKey: string;
  workspace: string;
  qrcodeUrl?: string;
  status: "waiting" | "connected" | "already_connected" | "failed";
  accountId?: string;
  userId?: string;
  message: string;
  startedAt: number;
};

type RuntimeState = {
  accountId: string;
  workspace: string;
  startedAt: number;
  running: boolean;
  lastEventAt?: number;
  lastInboundAt?: number;
  lastError?: string | null;
  abortController: AbortController;
};

type AgentInfo = {
  agentId: string;
  agentName: string;
};

type AgentSystemState = {
  active: boolean;
  awaitingChoice: boolean;
  selectedAgentId?: string;
  selectedAgentName?: string;
};

const DEFAULT_PORT = 8787;
const DEFAULT_ORCHESTRATOR_URL = "http://localhost:8001";
const BUSINESS_BRANCH_AGENT_NAME = "business_branch";
const loginStates = new Map<string, LoginState>();
const runtimes = new Map<string, RuntimeState>();
const agentSystemSessions = new Map<string, AgentSystemState>();

type PersistedRuntimeEntry = {
  workspace: string;
  updatedAt: string;
};

type PersistedRuntimeStore = {
  version: 1;
  accounts: Record<string, PersistedRuntimeEntry>;
};

function getBridgePort(): number {
  const raw = process.env.WEIXIN_BRIDGE_PORT?.trim();
  const port = raw ? Number(raw) : DEFAULT_PORT;
  return Number.isFinite(port) && port > 0 ? port : DEFAULT_PORT;
}

function getOrchestratorUrl(): string {
  return (process.env.AGENT_ORCHESTRATOR_URL || DEFAULT_ORCHESTRATOR_URL).replace(/\/$/, "");
}

function sendJson(res: http.ServerResponse, statusCode: number, payload: JsonRecord): void {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  res.end(body);
}

function readJson(req: http.IncomingMessage): Promise<JsonRecord> {
  return new Promise((resolve, reject) => {
    let body = "";
    req.setEncoding("utf-8");
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1024 * 1024) {
        req.destroy(new Error("request body too large"));
      }
    });
    req.on("end", () => {
      if (!body.trim()) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(body) as JsonRecord);
      } catch (err) {
        reject(err);
      }
    });
    req.on("error", reject);
  });
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function safeSessionPart(value: string): string {
  return value
    .trim()
    .replace(/[^A-Za-z0-9_-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80) || "unknown";
}

function buildWeixinSessionId(message: ProcessedWeixinMessage): string {
  return [
    "weixin",
    safeSessionPart(message.accountId),
    safeSessionPart(message.ctx.From),
  ].join("_");
}

function buildAgentSystemKey(message: ProcessedWeixinMessage): string {
  return [safeSessionPart(message.accountId), safeSessionPart(message.ctx.From)].join(":");
}

function resolveRuntimeStorePath(): string {
  return path.join(resolveStateDir(), "weixin-ilink", "bridge-runtimes.json");
}

function readPersistedRuntimeStore(): PersistedRuntimeStore {
  const filePath = resolveRuntimeStorePath();
  try {
    if (!fs.existsSync(filePath)) {
      return { version: 1, accounts: {} };
    }
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf-8")) as Partial<PersistedRuntimeStore>;
    const accounts: Record<string, PersistedRuntimeEntry> = {};
    for (const [accountId, entry] of Object.entries(parsed.accounts || {})) {
      if (!entry || typeof entry !== "object") continue;
      const workspace = typeof entry.workspace === "string" ? entry.workspace.trim() : "";
      if (!accountId.trim() || !workspace) continue;
      accounts[accountId] = {
        workspace,
        updatedAt: typeof entry.updatedAt === "string" ? entry.updatedAt : "",
      };
    }
    return { version: 1, accounts };
  } catch (err) {
    console.error(`[weixin-bridge] failed to read runtime store: ${String(err)}`);
    return { version: 1, accounts: {} };
  }
}

function writePersistedRuntimeStore(store: PersistedRuntimeStore): void {
  const filePath = resolveRuntimeStorePath();
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, JSON.stringify(store, null, 2), "utf-8");
  } catch (err) {
    console.error(`[weixin-bridge] failed to write runtime store: ${String(err)}`);
  }
}

function rememberRuntimeWorkspace(accountId: string, workspace: string): void {
  const normalizedAccountId = safeSessionPart(accountId);
  const normalizedWorkspace = workspace.trim();
  if (!normalizedAccountId || !normalizedWorkspace) return;
  const store = readPersistedRuntimeStore();
  store.accounts[normalizedAccountId] = {
    workspace: normalizedWorkspace,
    updatedAt: new Date().toISOString(),
  };
  writePersistedRuntimeStore(store);
}

function forgetRuntimeWorkspace(accountId: string): void {
  const normalizedAccountId = safeSessionPart(accountId);
  const store = readPersistedRuntimeStore();
  if (!(normalizedAccountId in store.accounts)) return;
  delete store.accounts[normalizedAccountId];
  writePersistedRuntimeStore(store);
}

function resolveReusableAccountId(): string {
  const configuredAccounts = listWeixinAccountIds()
    .map((accountId) => resolveWeixinAccount(undefined, accountId))
    .filter((account) => account.configured);
  const account = configuredAccounts.at(-1);
  if (!account) {
    throw new Error("微信连接器已绑定，但本地没有可复用的账号凭据。请删除连接后重新扫码。");
  }
  return account.accountId;
}

async function fetchAgentList(): Promise<AgentInfo[]> {
  const response = await fetch(`${getOrchestratorUrl()}/agents`);
  const text = await response.text();
  let data: JsonRecord = {};
  try {
    data = text ? JSON.parse(text) as JsonRecord : {};
  } catch {
    data = {};
  }
  if (!response.ok) {
    throw new Error(asString(data.detail) || text || `orchestrator /agents failed: ${response.status}`);
  }

  const rawAgents = Array.isArray(data.agents) ? data.agents : [];
  return rawAgents.flatMap((raw) => {
    if (!raw || typeof raw !== "object") return [];
    const record = raw as JsonRecord;
    const agentName = asString(record.agent_name);
    if (!agentName) return [];
    return [{
      agentId: asString(record.agent_id),
      agentName,
    }];
  });
}

async function resolveBusinessBranchAgent(): Promise<AgentInfo> {
  const agents = await fetchAgentList().catch(() => []);
  const matched = agents.find((agent) => agent.agentName === BUSINESS_BRANCH_AGENT_NAME);
  return matched ?? {
    agentId: BUSINESS_BRANCH_AGENT_NAME,
    agentName: BUSINESS_BRANCH_AGENT_NAME,
  };
}

async function callWorkspaceAgent(
  workspace: string,
  message: ProcessedWeixinMessage,
  selectedAgent?: AgentSystemState,
): Promise<string> {
  const payload: JsonRecord = {
    workspace,
    user_input: message.ctx.Body,
    user_id: `weixin:${message.ctx.From}`,
    big_session_id: buildWeixinSessionId(message),
  };
  const selectedAgentRef = selectedAgent?.selectedAgentId || selectedAgent?.selectedAgentName;
  if (selectedAgentRef) {
    payload.agent_id = selectedAgentRef;
  }

  const response = await fetch(`${getOrchestratorUrl()}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const text = await response.text();
  let data: JsonRecord = {};
  try {
    data = text ? JSON.parse(text) as JsonRecord : {};
  } catch {
    data = {};
  }
  if (!response.ok) {
    throw new Error(asString(data.detail) || text || `orchestrator /chat failed: ${response.status}`);
  }
  return asString(data.answer);
}

function currentRuntimeForMessage(workspace: string, message: ProcessedWeixinMessage): RuntimeState | undefined {
  return runtimes.get(message.accountId) ?? Array.from(runtimes.values()).find((item) => item.workspace === workspace);
}

function agentSystemHelp(): string {
  return [
    "已进入 Agent 管理模式。",
    "可用命令：",
    "Agent status 查看当前 Agent 状态",
    "Agent choose 选择你希望使用的 Agent",
    "out 退出 Agent 管理模式",
  ].join("\n");
}

async function handleAgentSystemMessage(workspace: string, message: ProcessedWeixinMessage): Promise<boolean> {
  const body = message.ctx.Body.trim();
  const normalized = body.toLowerCase();
  const key = buildAgentSystemKey(message);
  const existing = agentSystemSessions.get(key);

  if (normalized === "agent system") {
    agentSystemSessions.set(key, {
      active: true,
      awaitingChoice: false,
      selectedAgentId: existing?.selectedAgentId,
      selectedAgentName: existing?.selectedAgentName,
    });
    await message.replyText(agentSystemHelp());
    return true;
  }

  if (!existing?.active) {
    return false;
  }

  if (normalized === "out") {
    agentSystemSessions.set(key, { ...existing, active: false, awaitingChoice: false });
    await message.replyText("已退出 Agent 管理模式。");
    return true;
  }

  if (existing.awaitingChoice) {
    if (body === BUSINESS_BRANCH_AGENT_NAME) {
      const agent = await resolveBusinessBranchAgent();
      agentSystemSessions.set(key, {
        active: true,
        awaitingChoice: false,
        selectedAgentId: agent.agentId,
        selectedAgentName: agent.agentName,
      });
      await message.replyText(`已选择 Agent：${agent.agentName}`);
      return true;
    }
    await message.replyText(`当前只支持选择：${BUSINESS_BRANCH_AGENT_NAME}\n请直接输入 ${BUSINESS_BRANCH_AGENT_NAME}，或输入 out 退出。`);
    return true;
  }

  if (normalized === "agent choose") {
    const agent = await resolveBusinessBranchAgent();
    agentSystemSessions.set(key, { ...existing, awaitingChoice: true });
    const suffix = agent.agentId && agent.agentId !== agent.agentName ? ` (${agent.agentId})` : "";
    await message.replyText(`可选择的 Agent：\n${agent.agentName}${suffix}\n\n请输入 ${BUSINESS_BRANCH_AGENT_NAME} 完成选择。`);
    return true;
  }

  if (normalized === "agent status") {
    const runtime = currentRuntimeForMessage(workspace, message);
    const selectedName = existing.selectedAgentName || "未选择";
    const selectedId = existing.selectedAgentId || "未持久化";
    const runningText = runtime?.running ? "running" : "stopped";
    await message.replyText([
      "Agent 管理模式：已开启",
      `当前 Agent：${selectedName}`,
      `Agent ID：${selectedId}`,
      `微信运行状态：${runningText}`,
      `workspace：${runtime?.workspace || workspace}`,
      runtime?.lastError ? `最近错误：${runtime.lastError}` : "",
    ].filter(Boolean).join("\n"));
    return true;
  }

  await message.replyText("未知 Agent 管理命令。可输入 Agent status、Agent choose 或 out。");
  return true;
}

async function handleWeixinMessage(workspace: string, message: ProcessedWeixinMessage): Promise<void> {
  if (await handleAgentSystemMessage(workspace, message)) {
    return;
  }

  const selectedAgent = agentSystemSessions.get(buildAgentSystemKey(message));
  const answer = await callWorkspaceAgent(workspace, message, selectedAgent);
  await message.replyText(answer || "Agent returned an empty response.");
}

function serializeRuntime(state: RuntimeState): JsonRecord {
  return {
    accountId: state.accountId,
    workspace: state.workspace,
    running: state.running,
    startedAt: state.startedAt,
    lastEventAt: state.lastEventAt,
    lastInboundAt: state.lastInboundAt,
    lastError: state.lastError,
  };
}

async function startRuntime(accountId: string, workspace: string): Promise<RuntimeState> {
  const account = resolveWeixinAccount(undefined, accountId);
  const runtimeAccountId = account.accountId;
  const previous = runtimes.get(runtimeAccountId);
  if (previous) {
    previous.abortController.abort();
    await stopWeixinAccount({ accountId: runtimeAccountId }).catch(() => {});
  }

  const abortController = new AbortController();
  const state: RuntimeState = {
    accountId: runtimeAccountId,
    workspace,
    startedAt: Date.now(),
    running: true,
    abortController,
  };
  runtimes.set(runtimeAccountId, state);
  rememberRuntimeWorkspace(runtimeAccountId, workspace);

  void startWeixinAccount({
    accountId: runtimeAccountId,
    abortSignal: abortController.signal,
    setStatus: (next) => {
      const current = runtimes.get(runtimeAccountId);
      if (!current) return;
      if (typeof next.running === "boolean") current.running = next.running;
      if (next.lastEventAt !== undefined) current.lastEventAt = next.lastEventAt;
      if (next.lastInboundAt !== undefined) current.lastInboundAt = next.lastInboundAt;
      if (next.lastError !== undefined) current.lastError = next.lastError;
    },
    runtime: {
      log: (msg) => console.log(msg),
      error: (msg) => console.error(msg),
    },
    onMessage: (message) => handleWeixinMessage(workspace, message),
  }).catch((err) => {
    const current = runtimes.get(runtimeAccountId);
    if (current && current.abortController === abortController) {
      current.running = false;
      current.lastError = String(err);
    }
    console.error(`[weixin-bridge] runtime failed for ${runtimeAccountId}:`, err);
  });

  return state;
}

async function restorePersistedRuntimes(): Promise<void> {
  const store = readPersistedRuntimeStore();
  const configuredAccounts = new Set(
    listWeixinAccountIds()
      .map((accountId) => resolveWeixinAccount(undefined, accountId))
      .filter((account) => account.configured)
      .map((account) => account.accountId),
  );

  for (const [accountId, entry] of Object.entries(store.accounts)) {
    if (!configuredAccounts.has(accountId)) {
      forgetRuntimeWorkspace(accountId);
      continue;
    }
    if (runtimes.has(accountId)) continue;
    try {
      const runtime = await startRuntime(accountId, entry.workspace);
      console.log(`[weixin-bridge] restored account runtime ${runtime.accountId}`);
    } catch (err) {
      console.error(`[weixin-bridge] failed to restore account ${accountId}: ${String(err)}`);
    }
  }
}

function waitForLoginInBackground(sessionKey: string): void {
  void loginWithQrWait({ sessionKey, timeoutMs: 480_000 }).then(async (result) => {
    const state = loginStates.get(sessionKey);
    if (!state) return;
    if (result.connected && result.accountId) {
      state.status = "connected";
      state.userId = result.userId;
      state.message = result.message;
      const runtime = await startRuntime(result.accountId, state.workspace);
      state.accountId = runtime.accountId;
      return;
    }
    if (result.alreadyConnected) {
      const accountId = resolveReusableAccountId();
      const runtime = await startRuntime(accountId, state.workspace);
      state.status = "connected";
      state.accountId = runtime.accountId;
      state.message = "微信已连接，当前 Agent 已启动。";
      return;
    }
    state.status = "failed";
    state.message = result.message;
  }).catch((err) => {
    const state = loginStates.get(sessionKey);
    if (!state) return;
    state.status = "failed";
    state.message = String(err);
  });
}

async function route(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
  if (req.method === "OPTIONS") {
    sendJson(res, 204, {});
    return;
  }

  const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
  if (req.method === "GET" && url.pathname === "/health") {
    sendJson(res, 200, { status: "ok" });
    return;
  }

  if (req.method === "POST" && url.pathname === "/login/start") {
    const body = await readJson(req);
    const workspace = asString(body.workspace);
    if (!workspace) {
      sendJson(res, 400, { detail: "workspace is required" });
      return;
    }
    const start = await loginWithQrStart({ force: body.force === true });
    const state: LoginState = {
      sessionKey: start.sessionKey,
      workspace,
      qrcodeUrl: start.qrcodeUrl,
      status: start.qrcodeUrl ? "waiting" : "failed",
      message: start.message,
      startedAt: Date.now(),
    };
    loginStates.set(start.sessionKey, state);
    if (start.qrcodeUrl) {
      waitForLoginInBackground(start.sessionKey);
    }
    sendJson(res, start.qrcodeUrl ? 200 : 500, state);
    return;
  }

  if (req.method === "GET" && url.pathname === "/login/status") {
    const sessionKey = url.searchParams.get("sessionKey") || "";
    const state = loginStates.get(sessionKey);
    if (!state) {
      sendJson(res, 404, { detail: "login session not found" });
      return;
    }
    sendJson(res, 200, state);
    return;
  }

  if (req.method === "GET" && url.pathname === "/accounts") {
    const accounts = listWeixinAccountIds().map((accountId) => {
      const account = resolveWeixinAccount(undefined, accountId);
      const runtime = runtimes.get(account.accountId);
      return {
        accountId: account.accountId,
        configured: account.configured,
        running: runtime?.running ?? false,
        runtime: runtime ? serializeRuntime(runtime) : undefined,
      };
    });
    sendJson(res, 200, { accounts });
    return;
  }

  const accountStartMatch = url.pathname.match(/^\/accounts\/([^/]+)\/start$/);
  if (req.method === "POST" && accountStartMatch) {
    const body = await readJson(req);
    const workspace = asString(body.workspace);
    if (!workspace) {
      sendJson(res, 400, { detail: "workspace is required" });
      return;
    }
    const state = await startRuntime(decodeURIComponent(accountStartMatch[1]), workspace);
    sendJson(res, 200, serializeRuntime(state));
    return;
  }

  const accountMatch = url.pathname.match(/^\/accounts\/([^/]+)$/);
  if (accountMatch && req.method === "DELETE") {
    const requestedAccountId = decodeURIComponent(accountMatch[1]);
    const accountId = resolveWeixinAccount(undefined, requestedAccountId).accountId;
    const runtime = runtimes.get(accountId);
    if (runtime) {
      runtime.abortController.abort();
      runtimes.delete(accountId);
    }
    await stopWeixinAccount({ accountId }).catch(() => {});
    clearWeixinAccount(accountId);
    unregisterWeixinAccountId(accountId);
    forgetRuntimeWorkspace(accountId);
    sendJson(res, 200, { accountId, deleted: true });
    return;
  }

  sendJson(res, 404, { detail: "not found" });
}

const server = http.createServer((req, res) => {
  route(req, res).catch((err) => {
    console.error("[weixin-bridge] request failed:", err);
    sendJson(res, 500, { detail: String(err) });
  });
});

server.listen(getBridgePort(), () => {
  console.log(`[weixin-bridge] listening on http://localhost:${getBridgePort()}`);
  console.log(`[weixin-bridge] orchestrator ${getOrchestratorUrl()}`);
  void restorePersistedRuntimes();
});
