'use strict';

import { uid, truncate } from './dom.js';

const STORAGE_KEY = 'agent_chat_conversations_v1';

function readAll() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

function writeAll(list) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
}

export function listConversations() {
    return readAll().sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getConversation(id) {
    return readAll().find((c) => c.id === id) || null;
}

export function createConversation(title) {
    const now = Date.now();
    const conv = {
        id: uid('conv'),
        title: title || 'New chat',
        createdAt: now,
        updatedAt: now,
        messages: [],
    };
    const all = readAll();
    all.unshift(conv);
    writeAll(all);
    return conv;
}

export function updateConversation(id, patch) {
    const all = readAll();
    const idx = all.findIndex((c) => c.id === id);
    if (idx < 0) return null;
    all[idx] = { ...all[idx], ...patch, updatedAt: Date.now() };
    writeAll(all);
    return all[idx];
}

export function deleteConversation(id) {
    const all = readAll().filter((c) => c.id !== id);
    writeAll(all);
}

export function appendMessage(conversationId, message) {
    const all = readAll();
    const idx = all.findIndex((c) => c.id === conversationId);
    if (idx < 0) return null;
    const conv = all[idx];
    const nextMsg = {
        id: uid('msg'),
        role: message.role,
        content: message.content || '',
        attachments: message.attachments || [],
        createdAt: Date.now(),
    };
    conv.messages.push(nextMsg);
    if (conv.messages.length === 1 && message.role === 'user') {
        conv.title = truncate(message.content, 28);
    }
    conv.updatedAt = Date.now();
    all[idx] = conv;
    writeAll(all);
    return nextMsg;
}

export function toApiHistory(messages) {
    const pairs = [];
    let pendingUser = null;
    messages.forEach((m) => {
        if (m.role === 'user') {
            pendingUser = m.content;
        } else if (m.role === 'assistant' && pendingUser != null) {
            pairs.push({ human: pendingUser, assistant: m.content });
            pendingUser = null;
        }
    });
    return pairs;
}
