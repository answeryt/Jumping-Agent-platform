/**
 * Standalone placeholder for the old hook surface.
 * The connector no longer depends on host-provided hooks; callers can wrap send helpers
 * themselves if they need interception.
 */
export async function applyWeixinMessageSendingHook(params: {
  to: string;
  text: string;
  accountId?: string;
  mediaUrl?: string;
}): Promise<{ cancelled: boolean; text: string }> {
  void params.to;
  void params.accountId;
  void params.mediaUrl;
  return { cancelled: false, text: params.text };
}

export function emitWeixinMessageSent(params: {
  to: string;
  content: string;
  success: boolean;
  error?: string;
  accountId?: string;
}): void {
  void params;
}
