'use strict';

/** Generic block container tag (avoids mistaken replacement in some environments) */
export const BOX = ['d', 'i', 'v'].join('');

/**
 * Lightweight DOM helpers: build UI in pure JS without HTML templates.
 * @param {string} tag HTML tag name; use `box` for a generic div container
 */
export function el(tag, props, ...children) {
    const node = document.createElement(tag === 'box' ? BOX : tag);
    if (props) {
        Object.entries(props).forEach(([key, value]) => {
            if (value == null) return;
            if (key === 'className') {
                node.className = value;
            } else if (key === 'dataset') {
                Object.assign(node.dataset, value);
            } else if (key === 'style' && typeof value === 'object') {
                Object.assign(node.style, value);
            } else if (key.startsWith('on') && typeof value === 'function') {
                node.addEventListener(key.slice(2).toLowerCase(), value);
            } else if (key === 'html') {
                node.innerHTML = value;
            } else if (key === 'text') {
                node.textContent = value;
            } else if (key === 'attrs') {
                Object.entries(value).forEach(([attr, attrVal]) => {
                    if (attrVal != null) node.setAttribute(attr, attrVal);
                });
            } else {
                node.setAttribute(key, value);
            }
        });
    }
    const append = (child) => {
        if (child == null || child === false) return;
        if (Array.isArray(child)) {
            child.forEach(append);
            return;
        }
        if (child instanceof Node) {
            node.appendChild(child);
            return;
        }
        node.appendChild(document.createTextNode(String(child)));
    };
    children.forEach(append);
    return node;
}

export function svgIcon(pathD, viewBox) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', viewBox || '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('fill', 'currentColor');
    path.setAttribute('d', pathD);
    svg.appendChild(path);
    return svg;
}

export function formatTime(ts) {
    const d = new Date(ts);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function formatRelativeGroup(ts) {
    const now = new Date();
    const d = new Date(ts);
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startOfYesterday = startOfToday - 86400000;
    const t = d.getTime();
    if (t >= startOfToday) return 'Today';
    if (t >= startOfYesterday) return 'Yesterday';
    if (now.getFullYear() === d.getFullYear()) {
        return `${d.toLocaleString('en-US', { month: 'short' })} ${d.getDate()}`;
    }
    return `${d.getFullYear()} ${d.toLocaleString('en-US', { month: 'short' })}`;
}

export function truncate(text, max) {
    const s = (text || '').trim().replace(/\s+/g, ' ');
    if (s.length <= max) return s || 'New chat';
    return `${s.slice(0, max)}…`;
}

export function formatMessageText(text) {
    const s = String(text || '');
    if (!/\\(?:r\\n|[nrt"'\\]|u[0-9a-fA-F]{4}|u\{[0-9a-fA-F]+\})/.test(s)) {
        return s;
    }

    const decodeCodePoint = (hex) => {
        try {
            const codePoint = Number.parseInt(hex, 16);
            return Number.isFinite(codePoint) ? String.fromCodePoint(codePoint) : `\\u${hex}`;
        } catch {
            return `\\u${hex}`;
        }
    };

    return s
        .replace(/\\u\{([0-9a-fA-F]+)\}/g, (_, hex) => decodeCodePoint(hex))
        .replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => decodeCodePoint(hex))
        .replace(/\\r\\n/g, '\n')
        .replace(/\\n/g, '\n')
        .replace(/\\r/g, '\n')
        .replace(/\\t/g, '\t')
        .replace(/\\"/g, '"')
        .replace(/\\'/g, "'")
        .replace(/\\\\/g, '\\');
}

export function uid(prefix) {
    return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}
