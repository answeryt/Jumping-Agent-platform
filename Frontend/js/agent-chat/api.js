'use strict';

const ORCHESTRATOR_PORT = '8001';
const DEFAULT_API_URL = `http://localhost:${ORCHESTRATOR_PORT}/chat`;

function getDefaultApiUrl() {
    if (typeof window === 'undefined' || !window.location || !window.location.hostname) {
        return DEFAULT_API_URL;
    }
    return `${window.location.protocol}//${window.location.hostname}:${ORCHESTRATOR_PORT}/chat`;
}

export function getApiUrl() {
    if (typeof window !== 'undefined' && window.AGENT_CHAT_API_URL) {
        return window.AGENT_CHAT_API_URL;
    }
    return getDefaultApiUrl();
}

export function getOrchestratorBaseUrl() {
    return getApiUrl().replace(/\/chat\/?$/, '');
}

export function getSandboxPublicHost() {
    if (typeof window === 'undefined') return '';
    return window.AGENT_CHAT_SANDBOX_PUBLIC_HOST || '';
}

/**
 * @param {{
 *   userInput: string,
 *   history?: Array<{human:string, assistant:string}>,
 *   workspace?: string,
 *   agentId?: string,
 *   bigSessionId?: string,
 *   smallSessionId?: string,
 *   userId?: string
 * }} payload
 */
export async function sendChat(payload) {
    const res = await fetch(getApiUrl(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_input: payload.userInput,
            history: payload.history || [],
            workspace: payload.workspace || '',
            agent_id: payload.agentId || '',
            user_id: payload.userId || undefined,
            big_session_id: payload.bigSessionId || undefined,
            small_session_id: payload.smallSessionId || undefined,
        }),
    });
    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(text || `Request failed (${res.status})`);
    }
    return res.json();
}

/**
 * @param {{ userId?: string }} [payload]
 */
export async function createNewBigSession(payload = {}) {
    const res = await fetch(`${getOrchestratorBaseUrl()}/new-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            user_id: payload.userId || undefined,
        }),
    });
    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(text || `Failed to create session (${res.status})`);
    }
    return res.json();
}

/**
 * @param {{ workspace?: string }} payload
 */
export async function fetchWorkspaceSandboxes(payload) {
    const res = await fetch(`${getOrchestratorBaseUrl()}/workspace-sandboxes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            workspace: payload.workspace || '',
        }),
    });
    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(text || `Sandbox info request failed (${res.status})`);
    }
    return res.json();
}

/**
 * Subscribe to backend sandbox tool execution events via SSE. Returns a
 * disposer that closes the stream.
 *
 * @param {(event: any) => void} onEvent
 * @returns {() => void}
 */
export function subscribeSandboxEvents(onEvent) {
    if (typeof window === 'undefined' || typeof window.EventSource !== 'function') {
        return () => {};
    }
    const source = new EventSource(`${getOrchestratorBaseUrl()}/sandbox/events/stream`);
    source.onmessage = (msg) => {
        if (!msg || !msg.data) return;
        try {
            onEvent(JSON.parse(msg.data));
        } catch {
            /* swallow malformed event */
        }
    };
    source.onerror = () => {
        /* let the browser auto-reconnect */
    };
    return () => source.close();
}
