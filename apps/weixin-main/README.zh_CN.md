# 微信 iLink 连接器

这是一个独立的微信 iLink 连接器，保留扫码登录、账号存储、长轮询、文本回复、媒体上传下载等协议能力。

## 保留能力

- 扫码登录：`loginWithQr`、`loginWithQrStart`、`loginWithQrWait`。
- 账号存储：`saveWeixinAccount`、`loadWeixinAccount`、账号索引相关 helper。
- 长轮询：`startWeixinAccount` 或 `monitorWeixinProvider`。
- HTTP API 封装：`getUpdates`、`sendMessage`、`getUploadUrl`、`getConfig`、输入状态。
- 文本发送：`sendWeixinText` / `sendMessageWeixin`。
- 媒体发送与 CDN：`sendWeixinMedia`、`sendWeixinMediaFile`、`src/cdn/*`。

## 基本接入方式

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

连接器只负责微信协议层。Agent 路由、会话管理和执行逻辑由调用方通过 `onMessage` 注入。
