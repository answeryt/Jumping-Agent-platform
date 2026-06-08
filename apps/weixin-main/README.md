# Weixin iLink Connector

Standalone Weixin iLink connector for QR login, account storage, long polling, text replies, and media upload/download.

## Capabilities

- QR login via `loginWithQr`, `loginWithQrStart`, and `loginWithQrWait`.
- Local account storage via `saveWeixinAccount`, `loadWeixinAccount`, and account index helpers.
- Long polling via `startWeixinAccount` or `monitorWeixinProvider`.
- HTTP API wrappers for `getUpdates`, `sendMessage`, `getUploadUrl`, `getConfig`, and typing indicators.
- Text sending via `sendWeixinText` / `sendMessageWeixin`.
- Media sending and CDN helpers via `sendWeixinMedia`, `sendWeixinMediaFile`, and `src/cdn/*`.

## Basic Usage

```ts
import { loginWithQr, startWeixinAccount } from "@tencent-weixin/weixin-ilink";

await loginWithQr();

await startWeixinAccount({
  accountId: "your-account-id",
  onMessage: async (message) => {
    const answer = await yourAgentRuntime.chat(message.ctx.Body, {
      userId: `weixin:${message.ctx.From}`,
      sessionId: `weixin:${message.accountId}:${message.ctx.From}`,
    });

    await message.replyText(answer);
  },
});
```

The connector owns the Weixin protocol surface only. Routing, session management, and Agent execution are supplied by the caller through `onMessage`.
