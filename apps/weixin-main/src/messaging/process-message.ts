import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { sendTyping } from "../api/api.js";
import type { WeixinApiOptions } from "../api/api.js";
import type { MessageItem, WeixinMessage } from "../api/types.js";
import { MessageItemType, TypingStatus } from "../api/types.js";
import { downloadMediaFromItem } from "../media/media-download.js";
import { logger } from "../util/logger.js";
import { redactBody, redactToken } from "../util/redact.js";

import { isDebugMode } from "./debug-mode.js";
import { sendWeixinErrorNotice } from "./error-notice.js";
import { setContextToken, weixinMessageToMsgContext, getContextTokenFromMsgContext, isMediaItem } from "./inbound.js";
import type { WeixinInboundMediaOpts, WeixinMsgContext } from "./inbound.js";
import { sendWeixinMediaFile } from "./send-media.js";
import { StreamingMarkdownFilter } from "./markdown-filter.js";
import { sendMessageWeixin } from "./send.js";
import { handleSlashCommand } from "./slash-commands.js";

const MEDIA_OUTBOUND_TEMP_DIR = path.join(os.tmpdir(), "weixin-ilink", "media", "outbound-temp");
const INBOUND_MEDIA_MAX_BYTES = 100 * 1024 * 1024;

export type WeixinReplyPayload = {
  text?: string;
  mediaUrl?: string;
  mediaUrls?: string[];
};

export type ProcessedWeixinMessage = {
  raw: WeixinMessage;
  ctx: WeixinMsgContext;
  accountId: string;
  contextToken?: string;
  receivedAt: number;
  replyText: (text: string) => Promise<{ messageId: string }>;
  replyMedia: (params: { filePath: string; text?: string }) => Promise<{ messageId: string }>;
  reply: (payload: WeixinReplyPayload) => Promise<void>;
};

export type ProcessMessageDeps = {
  accountId: string;
  baseUrl: string;
  cdnBaseUrl: string;
  token?: string;
  typingTicket?: string;
  log: (msg: string) => void;
  errLog: (msg: string) => void;
  saveMedia?: SaveMediaFn;
  onMessage?: (message: ProcessedWeixinMessage) => Promise<void> | void;
};

type SaveMediaFn = (
  buffer: Buffer,
  contentType?: string,
  subdir?: string,
  maxBytes?: number,
  originalFilename?: string,
) => Promise<{ path: string }>;

function extractTextBody(itemList?: MessageItem[]): string {
  if (!itemList?.length) return "";
  for (const item of itemList) {
    if (item.type === MessageItemType.TEXT && item.text_item?.text != null) {
      return String(item.text_item.text);
    }
  }
  return "";
}

async function saveMediaToTemp(
  buffer: Buffer,
  _contentType?: string,
  subdir = "inbound",
  maxBytes = INBOUND_MEDIA_MAX_BYTES,
  originalFilename?: string,
): Promise<{ path: string }> {
  if (buffer.length > maxBytes) {
    throw new Error(`media exceeds max size: ${buffer.length} > ${maxBytes}`);
  }
  const dir = path.join(os.tmpdir(), "weixin-ilink", "media", subdir);
  await fs.promises.mkdir(dir, { recursive: true });
  const safeName =
    originalFilename?.replace(/[\\/:*?"<>|]/g, "_") ||
    `media-${Date.now()}-${Math.random().toString(16).slice(2)}.bin`;
  const filePath = path.join(dir, safeName);
  await fs.promises.writeFile(filePath, buffer);
  return { path: filePath };
}

function resolveLocalPath(mediaUrl: string): string {
  if (mediaUrl.startsWith("file://")) return new URL(mediaUrl).pathname;
  return path.isAbsolute(mediaUrl) ? mediaUrl : path.resolve(mediaUrl);
}

async function downloadRemoteMediaToTemp(mediaUrl: string): Promise<string> {
  const res = await fetch(mediaUrl);
  if (!res.ok) {
    throw new Error(`remote media download failed: ${res.status} ${res.statusText}`);
  }
  const arrayBuffer = await res.arrayBuffer();
  const buffer = Buffer.from(arrayBuffer);
  await fs.promises.mkdir(MEDIA_OUTBOUND_TEMP_DIR, { recursive: true });
  const urlPath = new URL(mediaUrl).pathname;
  const ext = path.extname(urlPath) || ".bin";
  const filePath = path.join(
    MEDIA_OUTBOUND_TEMP_DIR,
    `remote-${Date.now()}-${Math.random().toString(16).slice(2)}${ext}`,
  );
  await fs.promises.writeFile(filePath, buffer);
  return filePath;
}

async function withTyping<T>(deps: ProcessMessageDeps, to: string, run: () => Promise<T>): Promise<T> {
  const opts: WeixinApiOptions = { baseUrl: deps.baseUrl, token: deps.token };
  const canType = Boolean(deps.typingTicket);
  if (canType) {
    try {
      await sendTyping({
        ...opts,
        body: {
          ilink_user_id: to,
          typing_ticket: deps.typingTicket,
          status: TypingStatus.TYPING,
        },
      });
    } catch (err) {
      deps.log(`[weixin] typing send error: ${String(err)}`);
    }
  }

  try {
    return await run();
  } finally {
    if (canType) {
      try {
        await sendTyping({
          ...opts,
          body: {
            ilink_user_id: to,
            typing_ticket: deps.typingTicket,
            status: TypingStatus.CANCEL,
          },
        });
      } catch (err) {
        deps.log(`[weixin] typing cancel error: ${String(err)}`);
      }
    }
  }
}

export async function processOneMessage(
  full: WeixinMessage,
  deps: ProcessMessageDeps,
): Promise<void> {
  const receivedAt = Date.now();
  const debug = isDebugMode(deps.accountId);
  const debugTrace: string[] = [];
  const debugTs: Record<string, number> = { received: receivedAt };

  const textBody = extractTextBody(full.item_list);
  if (textBody.startsWith("/")) {
    const slashResult = await handleSlashCommand(textBody, {
      to: full.from_user_id ?? "",
      contextToken: full.context_token,
      baseUrl: deps.baseUrl,
      token: deps.token,
      accountId: deps.accountId,
      log: deps.log,
      errLog: deps.errLog,
    }, receivedAt, full.create_time_ms);
    if (slashResult.handled) {
      logger.info("[weixin] Slash command handled, skipping external message handler");
      return;
    }
  }

  if (debug) {
    const itemTypes = full.item_list?.map((i) => i.type).join(",") ?? "none";
    debugTrace.push(
      "-- inbound --",
      `seq=${full.seq ?? "?"} msgId=${full.message_id ?? "?"} from=${full.from_user_id ?? "?"}`,
      `body="${textBody.slice(0, 40)}${textBody.length > 40 ? "..." : ""}" len=${textBody.length} itemTypes=[${itemTypes}]`,
      `sessionId=${full.session_id ?? "?"} contextToken=${full.context_token ? "present" : "none"}`,
    );
  }

  const mediaOpts: WeixinInboundMediaOpts = {};
  const hasDownloadableMedia = (m?: { encrypt_query_param?: string; full_url?: string }) =>
    m?.encrypt_query_param || m?.full_url;
  const mainMediaItem =
    full.item_list?.find((i) => i.type === MessageItemType.IMAGE && hasDownloadableMedia(i.image_item?.media)) ??
    full.item_list?.find((i) => i.type === MessageItemType.VIDEO && hasDownloadableMedia(i.video_item?.media)) ??
    full.item_list?.find((i) => i.type === MessageItemType.FILE && hasDownloadableMedia(i.file_item?.media)) ??
    full.item_list?.find(
      (i) =>
        i.type === MessageItemType.VOICE &&
        hasDownloadableMedia(i.voice_item?.media) &&
        !i.voice_item?.text,
    );
  const refMediaItem = !mainMediaItem
    ? full.item_list?.find(
        (i) =>
          i.type === MessageItemType.TEXT &&
          i.ref_msg?.message_item &&
          isMediaItem(i.ref_msg.message_item),
      )?.ref_msg?.message_item
    : undefined;

  const mediaDownloadStart = Date.now();
  const mediaItem = mainMediaItem ?? refMediaItem;
  if (mediaItem) {
    const label = refMediaItem ? "ref" : "inbound";
    const downloaded = await downloadMediaFromItem(mediaItem, {
      cdnBaseUrl: deps.cdnBaseUrl,
      saveMedia: deps.saveMedia ?? saveMediaToTemp,
      log: deps.log,
      errLog: deps.errLog,
      label,
    });
    Object.assign(mediaOpts, downloaded);
  }
  const mediaDownloadMs = Date.now() - mediaDownloadStart;

  const ctx = weixinMessageToMsgContext(full, deps.accountId, mediaOpts);
  const contextToken = getContextTokenFromMsgContext(ctx);
  if (contextToken) {
    setContextToken(deps.accountId, full.from_user_id ?? "", contextToken);
  }

  logger.info(
    `inbound: from=${ctx.From} to=${ctx.To} bodyLen=${ctx.Body.length} hasMedia=${Boolean(ctx.MediaPath)}`,
  );
  logger.debug(`inbound context: ${redactBody(JSON.stringify(ctx))}`);

  const replyText = async (rawText: string): Promise<{ messageId: string }> => {
    const f = new StreamingMarkdownFilter();
    const text = f.feed(rawText ?? "") + f.flush();
    logger.info(
      `outbound: to=${ctx.To} contextToken=${redactToken(contextToken)} textLen=${text.length}`,
    );
    return sendMessageWeixin({
      to: ctx.To,
      text,
      opts: { baseUrl: deps.baseUrl, token: deps.token, contextToken },
    });
  };

  const replyMedia = async (params: { filePath: string; text?: string }): Promise<{ messageId: string }> => {
    return sendWeixinMediaFile({
      filePath: params.filePath,
      to: ctx.To,
      text: params.text ?? "",
      opts: { baseUrl: deps.baseUrl, token: deps.token, contextToken },
      cdnBaseUrl: deps.cdnBaseUrl,
    });
  };

  const reply = async (payload: WeixinReplyPayload): Promise<void> => {
    const mediaUrl = payload.mediaUrl ?? payload.mediaUrls?.[0];
    if (mediaUrl) {
      const filePath = mediaUrl.startsWith("http://") || mediaUrl.startsWith("https://")
        ? await downloadRemoteMediaToTemp(mediaUrl)
        : resolveLocalPath(mediaUrl);
      await replyMedia({ filePath, text: payload.text });
      return;
    }
    if (payload.text) {
      await replyText(payload.text);
    }
  };

  const event: ProcessedWeixinMessage = {
    raw: full,
    ctx,
    accountId: deps.accountId,
    contextToken,
    receivedAt,
    replyText,
    replyMedia,
    reply,
  };

  debugTs.preDispatch = Date.now();
  try {
    if (deps.onMessage) {
      await withTyping(deps, ctx.To, async () => {
        await deps.onMessage?.(event);
      });
    }
  } catch (err) {
    deps.errLog(`weixin message handler failed: ${String(err)}`);
    await sendWeixinErrorNotice({
      to: ctx.To,
      contextToken,
      message: `消息处理失败：${err instanceof Error ? err.message : String(err)}`,
      baseUrl: deps.baseUrl,
      token: deps.token,
      errLog: deps.errLog,
    });
    throw err;
  } finally {
    if (debug && contextToken) {
      const dispatchDoneAt = Date.now();
      const eventTs = full.create_time_ms ?? 0;
      const platformDelay = eventTs > 0 ? `${receivedAt - eventTs}ms` : "N/A";
      const inboundProcessMs = (debugTs.preDispatch ?? receivedAt) - receivedAt;
      const handlerMs = dispatchDoneAt - (debugTs.preDispatch ?? receivedAt);
      const totalTime = eventTs > 0 ? `${dispatchDoneAt - eventTs}ms` : `${dispatchDoneAt - receivedAt}ms`;

      debugTrace.push(
        "-- timing --",
        `platformToConnector=${platformDelay}`,
        `inboundProcess=${inboundProcessMs}ms mediaDownload=${mediaDownloadMs}ms`,
        `handlerAndReply=${handlerMs}ms`,
        `total=${totalTime}`,
      );

      try {
        await sendMessageWeixin({
          to: ctx.To,
          text: `Debug timing\n${debugTrace.join("\n")}`,
          opts: { baseUrl: deps.baseUrl, token: deps.token, contextToken },
        });
      } catch (debugErr) {
        logger.error(`debug-timing: send FAILED err=${String(debugErr)}`);
      }
    }
  }
}
