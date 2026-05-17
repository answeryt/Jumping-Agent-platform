'use strict';

import { el, svgIcon, formatTime, formatRelativeGroup, truncate, formatMessageText } from './dom.js';
import * as store from './store.js';
import {
    createNewBigSession,
    fetchWorkspaceSandboxes,
    getSandboxPublicHost,
    sendChat,
    subscribeSandboxEvents,
} from './api.js';

const ICONS = {
    plus: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
    send: 'M2.01 21L23 12 2.01 3 2 10l15 2-15 2z',
    menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
    arrowLeft: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.42-1.41L7.83 13H20v-2z',
    chat: 'M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z',
    computer: 'M20 18c1.1 0 1.99-.9 1.99-2L22 6c0-1.1-.9-2-2-2H4c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2H1v2h22v-2h-3zM4 6h16v10H4V6z',
    trash: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
    image: 'M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z',
    file: 'M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z',
    close: 'M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
};

const ACCEPT_IMAGE = 'image/png,image/jpeg,image/gif,image/webp,image/svg+xml';
const ACCEPT_FILE = '*/*';
const BUILT_AGENT_KEY = 'agent_builder_built_agents_v1';

function isLoopbackHost(hostname) {
    return hostname === 'localhost'
        || hostname === '0.0.0.0'
        || hostname === '::1'
        || hostname === '[::1]'
        || hostname.startsWith('127.');
}

function normalizeSandboxUrlForClient(url) {
    if (!url || typeof window === 'undefined' || !window.location?.hostname) {
        return url || '';
    }
    try {
        const parsed = new URL(url, window.location.href);
        if (isLoopbackHost(parsed.hostname)) {
            const publicHost = getSandboxPublicHost();
            if (publicHost) {
                parsed.hostname = publicHost;
            } else if (!isLoopbackHost(window.location.hostname)) {
                parsed.hostname = window.location.hostname;
            }
        }
        return parsed.toString();
    } catch {
        return url || '';
    }
}

export class AgentChatApp {
    constructor(root) {
        this.root = root;
        this.state = {
            conversationId: null,
            sidebarOpen: true,
            sending: false,
            pendingAttachments: [],
            attachMenuOpen: false,
            agentMenuOpen: false,
            selectedAgent: null,
            sidebarMode: 'history',
            selectedSandboxAgent: null,
            sandboxView: 'vnc',
            sandboxLoading: false,
            sandboxError: '',
            sandboxEvents: [],
        };
        this.refs = {};
        this._bindGlobal();
        this._mount();
        this._bootstrapConversation();
        this._sandboxEventsUnsubscribe = subscribeSandboxEvents((event) => this._onSandboxToolEvent(event));
    }

    _bindGlobal() {
        this._onDocClick = (e) => {
            if (!this.refs.attachMenu?.contains(e.target) && !this.refs.attachBtn?.contains(e.target)) {
                this._setAttachMenu(false);
            }
            if (!this.refs.agentMenu?.contains(e.target) && !this.refs.myAgentBtn?.contains(e.target)) {
                this._setAgentMenu(false);
            }
        };
        document.addEventListener('click', this._onDocClick);
        this._onResize = () => {
            if (window.innerWidth < 768 && this.state.sidebarOpen) {
                this._setSidebar(false);
            }
        };
        window.addEventListener('resize', this._onResize);
    }

    destroy() {
        document.removeEventListener('click', this._onDocClick);
        window.removeEventListener('resize', this._onResize);
        if (typeof this._sandboxEventsUnsubscribe === 'function') {
            try { this._sandboxEventsUnsubscribe(); } catch { /* noop */ }
        }
        this.root.innerHTML = '';
    }

    _mount() {
        this.root.className = 'agent-chat-root';
        this.root.innerHTML = '';

        this.refs.iconRail = this._buildIconRail();
        this.refs.sidebar = el('aside', { className: 'ac-sidebar' }, this._buildSidebarInner());
        this.refs.main = el('main', { className: 'ac-main' }, this._buildMainInner());
        this.refs.overlay = el('box', {
            className: 'ac-sidebar-overlay',
            onClick: () => this._setSidebar(false),
        });

        this.root.append(
            this.refs.overlay,
            this.refs.iconRail,
            this.refs.sidebar,
            this.refs.main,
        );

        this._onResize();
    }

    _buildIconRail() {
        this.refs.historyRailBtn = el(
            'button',
            {
                className: 'ac-rail-btn is-active',
                type: 'button',
                title: 'Chat history',
                onClick: () => this._showHistorySidebar(),
            },
            svgIcon(ICONS.chat),
        );
        this.refs.sandboxRailBtn = el(
            'button',
            {
                className: 'ac-rail-btn',
                type: 'button',
                title: 'Live sandbox',
                onClick: () => this._showSandboxSidebar(),
            },
            svgIcon(ICONS.computer),
        );
        return el('nav', { className: 'ac-icon-rail', attrs: { 'aria-label': 'Quick links' } }, [
            this.refs.historyRailBtn,
            this.refs.sandboxRailBtn,
        ]);
    }

    _buildSidebarInner() {
        this.refs.newChatBtn = el(
            'button',
            { className: 'ac-btn ac-btn-ghost ac-new-chat', type: 'button', onClick: () => this._newConversation() },
            svgIcon(ICONS.plus),
            ' New chat',
        );
        this.refs.historyList = el('div', { className: 'ac-history-list' });
        this.refs.collapseHistoryBtn = el(
            'button',
            { className: 'ac-sidebar-arrow-toggle', type: 'button', title: 'Collapse sidebar', onClick: () => this._collapseSidebar() },
            svgIcon(ICONS.arrowLeft),
        );
        this.refs.sidebarTitle = el('h2', { className: 'ac-sidebar-title', text: 'Chat history' });
        this.refs.sandboxPanel = el('box', { className: 'ac-sandbox-panel' });
        return [
            el('box', { className: 'ac-sidebar-top' }, [
                this.refs.collapseHistoryBtn,
                this.refs.sidebarTitle,
                this.refs.newChatBtn,
            ]),
            el('box', { className: 'ac-sidebar-scroll' }, [
                this.refs.historyList,
                this.refs.sandboxPanel,
            ]),
        ];
    }

    _buildMainInner() {
        this.refs.toggleSidebar = el(
            'button',
            { className: 'ac-icon-btn ac-toggle-sidebar', type: 'button', title: 'History', onClick: () => this._setSidebar(!this.state.sidebarOpen) },
            svgIcon(ICONS.menu),
        );
        this.refs.title = el('h1', { className: 'ac-title', text: 'New chat' });
        this.refs.myAgentBtn = el(
            'button',
            { className: 'ac-main-agent-btn', type: 'button', onClick: (e) => { e.stopPropagation(); this._setAgentMenu(!this.state.agentMenuOpen); } },
            'My Agent',
        );
        this.refs.agentMenu = el('box', { className: 'ac-agent-menu' });
        this.refs.mainAgentPanel = el('box', { className: 'ac-main-agent-panel' }, [
            this.refs.myAgentBtn,
            this.refs.agentMenu,
        ]);
        this.refs.messageList = el('box', { className: 'ac-messages' });
        this.refs.welcome = el('box', { className: 'ac-welcome' }, [
            el('h2', { text: 'How can I help you today?' }),
        ]);

        this.refs.attachmentPreview = el('box', { className: 'ac-attachment-preview' });
        this.refs.input = el('textarea', {
            className: 'ac-input',
            attrs: { rows: '1', placeholder: 'Send a message…' },
            onInput: (e) => this._autoResizeInput(e.target),
            onKeydown: (e) => this._onInputKeydown(e),
        });
        this.refs.fileImage = this._hiddenFileInput(ACCEPT_IMAGE, true);
        this.refs.fileAny = this._hiddenFileInput(ACCEPT_FILE, false);

        this.refs.attachMenu = el('box', { className: 'ac-attach-menu' }, [
            el('button', { type: 'button', onClick: () => { this.refs.fileImage.click(); this._setAttachMenu(false); } }, [
                svgIcon(ICONS.image),
                el('span', { text: 'Upload image' }),
            ]),
            el('button', { type: 'button', onClick: () => { this.refs.fileAny.click(); this._setAttachMenu(false); } }, [
                svgIcon(ICONS.file),
                el('span', { text: 'Upload file' }),
            ]),
        ]);

        this.refs.attachBtn = el(
            'button',
            { className: 'ac-icon-btn ac-attach-btn', type: 'button', title: 'Add attachment', onClick: (e) => { e.stopPropagation(); this._setAttachMenu(!this.state.attachMenuOpen); } },
            svgIcon(ICONS.plus),
        );

        this.refs.sendBtn = el(
            'button',
            { className: 'ac-icon-btn ac-send-btn', type: 'button', title: 'Send', onClick: () => this._sendMessage() },
            svgIcon(ICONS.send),
        );

        this.refs.composer = el('box', {
            className: 'ac-composer',
            onDragover: (e) => { e.preventDefault(); this.refs.composer.classList.add('is-dragover'); },
            onDragleave: () => this.refs.composer.classList.remove('is-dragover'),
            onDrop: (e) => this._onDrop(e),
        }, [
            this.refs.attachmentPreview,
            el('box', { className: 'ac-composer-row' }, [
                el('box', { className: 'ac-attach-wrap' }, [this.refs.attachBtn, this.refs.attachMenu]),
                this.refs.input,
                this.refs.sendBtn,
            ]),
        ]);

        this.refs.statusBar = el('box', { className: 'ac-status', text: '' });

        return [
            this.refs.mainAgentPanel,
            el('box', { className: 'ac-chat-body' }, [this.refs.welcome, this.refs.messageList]),
            el('footer', { className: 'ac-footer' }, [this.refs.composer, this.refs.statusBar]),
            this.refs.fileImage,
            this.refs.fileAny,
        ];
    }

    _hiddenFileInput(accept, imagesOnly) {
        return el('input', {
            type: 'file',
            attrs: { accept, multiple: 'multiple', hidden: 'hidden', tabindex: '-1' },
            onChange: (e) => {
                this._addFiles(e.target.files, imagesOnly);
                e.target.value = '';
            },
        });
    }

    _bootstrapConversation() {
        this.state.selectedAgent = this._readBuiltAgents()[0] || null;
        this.state.selectedSandboxAgent = this._firstSandboxName(this.state.selectedAgent);
        this._renderSelectedAgent();
        const list = store.listConversations();
        if (list.length) {
            this._selectConversation(list[0].id);
        } else {
            const conv = store.createConversation();
            this._selectConversation(conv.id);
        }
        this._renderHistory();
    }

    async _newConversation() {
        const conv = store.createConversation();
        this._selectConversation(conv.id);
        this._renderHistory();
        this.refs.input.focus();
        try {
            const session = await createNewBigSession();
            if (session && session.big_session_id) {
                store.updateConversation(conv.id, {
                    bigSessionId: session.big_session_id,
                    smallSessionId: null,
                    userId: session.user_id || null,
                });
                this._renderHistory();
            }
        } catch (err) {
            this._setStatus(`Failed to create big session: ${err.message || err}`, true);
        }
    }

    _onSandboxToolEvent(event) {
        if (!event || typeof event !== 'object') return;
        this.state.sandboxEvents = [event, ...this.state.sandboxEvents].slice(0, 30);
        const tool = event.tool_name || 'unknown';
        const status = event.status || '';
        const agent = event.agent_name || '';
        if (status === 'start') {
            this._setStatus(`${agent} calling sandbox tool: ${tool}…`);
        } else if (status === 'finish') {
            const ms = typeof event.duration_ms === 'number' ? `${event.duration_ms}ms` : '';
            this._setStatus(`${agent} ${tool} finished ${ms}`);
        } else if (status === 'error') {
            this._setStatus(`${agent} ${tool} failed: ${event.error || ''}`, true);
        }
    }

    _selectConversation(id) {
        this.state.conversationId = id;
        this.state.pendingAttachments = [];
        this._renderAttachments();
        const conv = store.getConversation(id);
        this.refs.title.textContent = conv?.title || 'New chat';
        this._renderMessages();
        this._renderHistory();
        if (window.innerWidth < 768) this._setSidebar(false);
    }

    _deleteConversation(id, e) {
        e.stopPropagation();
        store.deleteConversation(id);
        const list = store.listConversations();
        if (this.state.conversationId === id) {
            if (list.length) this._selectConversation(list[0].id);
            else {
                const conv = store.createConversation();
                this._selectConversation(conv.id);
            }
        }
        this._renderHistory();
    }

    _renderHistory() {
        const list = store.listConversations();
        const groups = new Map();
        list.forEach((c) => {
            const g = formatRelativeGroup(c.updatedAt);
            if (!groups.has(g)) groups.set(g, []);
            groups.get(g).push(c);
        });

        this.refs.historyList.innerHTML = '';
        groups.forEach((items, label) => {
            this.refs.historyList.appendChild(
                el('section', { className: 'ac-history-group' }, [
                    el('h3', { className: 'ac-history-label', text: label }),
                    el('ul', { className: 'ac-history-items' }, items.map((c) => this._historyItem(c))),
                ]),
            );
        });
    }

    _historyItem(conv) {
        const active = conv.id === this.state.conversationId;
        return el(
            'li',
            {
                className: `ac-history-item${active ? ' is-active' : ''}`,
                onClick: () => this._selectConversation(conv.id),
            },
            [
                el('span', { className: 'ac-history-title', text: truncate(conv.title, 32) }),
                el(
                    'button',
                    {
                        className: 'ac-history-delete',
                        type: 'button',
                        title: 'Delete',
                        onClick: (e) => this._deleteConversation(conv.id, e),
                    },
                    svgIcon(ICONS.trash),
                ),
            ],
        );
    }

    _renderMessages() {
        const conv = store.getConversation(this.state.conversationId);
        const messages = conv?.messages || [];
        this.refs.messageList.innerHTML = '';
        this.refs.welcome.style.display = messages.length ? 'none' : '';
        this.root.classList.toggle('has-messages', messages.length > 0);

        messages.forEach((msg) => {
            this.refs.messageList.appendChild(this._messageBubble(msg));
        });
        this._scrollToBottom();
    }

    _messageBubble(msg) {
        const isUser = msg.role === 'user';
        const body = [];

        if (msg.attachments?.length) {
            body.push(el('box', { className: 'ac-msg-attachments' }, msg.attachments.map((a) => this._attachmentChip(a, false))));
        }
        if (msg.content) {
            body.push(el('box', { className: 'ac-msg-text', text: formatMessageText(msg.content) }));
        }

        return el('article', { className: `ac-message${isUser ? ' is-user' : ' is-assistant'}` }, [
            el('box', { className: 'ac-msg-avatar', text: isUser ? 'You' : 'AI' }),
            el('box', { className: 'ac-msg-body' }, body),
            el('time', { className: 'ac-msg-time', text: formatTime(msg.createdAt) }),
        ]);
    }

    _attachmentChip(att, removable) {
        const isImage = att.kind === 'image' && att.previewUrl;
        const children = [];
        if (isImage) {
            children.push(el('img', { className: 'ac-att-thumb', attrs: { src: att.previewUrl, alt: att.name } }));
        } else {
            children.push(svgIcon(ICONS.file), el('span', { className: 'ac-att-name', text: att.name }));
        }
        if (removable) {
            children.push(
                el('button', {
                    className: 'ac-att-remove',
                    type: 'button',
                    title: 'Remove',
                    onClick: () => this._removePending(att.id),
                }, svgIcon(ICONS.close)),
            );
        }
        return el('box', { className: `ac-att-chip${isImage ? ' is-image' : ''}`, title: att.name }, children);
    }

    _renderAttachments() {
        this.refs.attachmentPreview.innerHTML = '';
        if (!this.state.pendingAttachments.length) {
            this.refs.attachmentPreview.style.display = 'none';
            return;
        }
        this.refs.attachmentPreview.style.display = '';
        this.state.pendingAttachments.forEach((a) => {
            this.refs.attachmentPreview.appendChild(this._attachmentChip(a, true));
        });
    }

    async _addFiles(fileList, imagesOnly) {
        const files = Array.from(fileList || []);
        for (const file of files) {
            if (imagesOnly && !file.type.startsWith('image/')) continue;
            const att = await this._fileToAttachment(file);
            this.state.pendingAttachments.push(att);
        }
        this._renderAttachments();
    }

    _fileToAttachment(file) {
        return new Promise((resolve) => {
            const base = {
                id: `att_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
                name: file.name,
                size: file.size,
                mime: file.type || 'application/octet-stream',
                kind: file.type.startsWith('image/') ? 'image' : 'file',
                previewUrl: null,
                dataUrl: null,
            };
            const reader = new FileReader();
            reader.onload = () => {
                base.dataUrl = reader.result;
                if (base.kind === 'image') base.previewUrl = reader.result;
                resolve(base);
            };
            reader.onerror = () => resolve(base);
            reader.readAsDataURL(file);
        });
    }

    _removePending(id) {
        this.state.pendingAttachments = this.state.pendingAttachments.filter((a) => a.id !== id);
        this._renderAttachments();
    }

    _onDrop(e) {
        e.preventDefault();
        this.refs.composer.classList.remove('is-dragover');
        this._addFiles(e.dataTransfer?.files, false);
    }

    _setAttachMenu(open) {
        this.state.attachMenuOpen = open;
        this.refs.attachMenu.classList.toggle('is-open', open);
    }

    _setAgentMenu(open) {
        this.state.agentMenuOpen = open;
        if (open) {
            this._renderAgentMenu();
        }
        this.refs.agentMenu.classList.toggle('is-open', open);
        this.refs.myAgentBtn.classList.toggle('is-open', open);
    }

    _readBuiltAgents() {
        try {
            const parsed = JSON.parse(localStorage.getItem(BUILT_AGENT_KEY) || '[]');
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    }

    _writeBuiltAgents(agents) {
        localStorage.setItem(BUILT_AGENT_KEY, JSON.stringify((agents || []).slice(0, 20)));
    }

    _renderAgentMenu() {
        const agents = this._readBuiltAgents();
        this.refs.agentMenu.innerHTML = '';
        this.refs.agentMenu.appendChild(el('h3', { text: 'Built agents' }));
        if (!agents.length) {
            this.refs.agentMenu.appendChild(el('p', { className: 'ac-agent-empty', text: 'No built agents yet.' }));
            return;
        }
        this.refs.agentMenu.appendChild(el('ul', { className: 'ac-agent-list' }, agents.map((agent) => (
            el('li', {
                className: `ac-agent-item${this.state.selectedAgent?.id === agent.id ? ' is-active' : ''}`,
                onClick: () => this._selectAgent(agent),
            }, [
                el('strong', { text: agent.name || 'My Agent' }),
                el('span', { text: agent.task || agent.flowType || 'No task set' }),
                agent.workspace ? el('small', { text: agent.workspace }) : null,
            ])
        ))));
    }

    _selectAgent(agent) {
        this.state.selectedAgent = agent || null;
        this.state.selectedSandboxAgent = this._firstSandboxName(agent);
        this._renderSelectedAgent();
        if (this.state.sidebarMode === 'sandbox') {
            this._renderSandboxPanel();
            this._ensureSelectedAgentSandboxes();
        }
        this._setAgentMenu(false);
        this._setStatus(agent?.workspace ? `Current agent: ${agent.name || 'My Agent'}` : 'Will use the latest built agent workspace');
    }

    _renderSelectedAgent() {
        if (!this.refs.myAgentBtn) return;
        const agent = this.state.selectedAgent;
        this.refs.myAgentBtn.textContent = agent ? (agent.name || 'My Agent') : 'My Agent';
        this.refs.myAgentBtn.title = agent?.workspace || 'Uses the latest backend workspace when none is selected';
    }

    _showHistorySidebar() {
        const wasSandbox = this.state.sidebarMode === 'sandbox';
        this._setSidebarMode('history');
        this._setSidebar(wasSandbox || !this.state.sidebarOpen);
    }

    _showSandboxSidebar() {
        this._setSidebarMode('sandbox');
        this._setSidebar(true);
        this._renderSandboxPanel();
        this._ensureSelectedAgentSandboxes();
    }

    _collapseSidebar() {
        if (this.state.sidebarMode === 'sandbox') {
            this._setSidebarMode('history');
            this._setSidebar(true);
            return;
        }
        this._setSidebar(false);
    }

    _setSidebarMode(mode) {
        this.state.sidebarMode = mode;
        this.root.classList.toggle('sidebar-mode-sandbox', mode === 'sandbox');
        this.root.classList.toggle('sidebar-mode-history', mode !== 'sandbox');
        if (this.refs.sidebarTitle) {
            this.refs.sidebarTitle.textContent = mode === 'sandbox' ? 'Sandbox' : 'Chat history';
        }
        if (this.refs.historyRailBtn) this.refs.historyRailBtn.classList.toggle('is-active', mode !== 'sandbox');
        if (this.refs.sandboxRailBtn) this.refs.sandboxRailBtn.classList.toggle('is-active', mode === 'sandbox');
    }

    _sandboxEntries(agent) {
        const sandboxes = agent?.sandboxes || {};
        return Object.entries(sandboxes).filter(([, sandbox]) => sandbox && (sandbox.dashboardUrl || sandbox.vncUrl || sandbox.baseUrl || sandbox.sandboxUrl));
    }

    _firstSandboxName(agent) {
        const first = this._sandboxEntries(agent)[0];
        return first ? first[0] : null;
    }

    _selectedSandboxEntry() {
        const entries = this._sandboxEntries(this.state.selectedAgent);
        if (!entries.length) return null;
        return entries.find(([name]) => name === this.state.selectedSandboxAgent) || entries[0];
    }

    async _ensureSelectedAgentSandboxes() {
        const agent = this.state.selectedAgent;
        if (!agent || this._sandboxEntries(agent).length || this.state.sandboxLoading) {
            return;
        }
        this.state.sandboxLoading = true;
        this.state.sandboxError = '';
        this._renderSandboxPanel();
        try {
            const data = await fetchWorkspaceSandboxes({ workspace: agent.workspace || '' });
            const sandboxes = data.sandboxes || {};
            const nextAgent = {
                ...agent,
                workspace: data.workspace || agent.workspace,
                sandboxes,
            };
            this.state.selectedAgent = nextAgent;
            this.state.selectedSandboxAgent = this._firstSandboxName(nextAgent);
            this._updateBuiltAgent(nextAgent);
        } catch (err) {
            this.state.sandboxError = err.message || String(err);
        } finally {
            this.state.sandboxLoading = false;
            this._renderSandboxPanel();
        }
    }

    _updateBuiltAgent(nextAgent) {
        const agents = this._readBuiltAgents();
        const index = agents.findIndex((item) => item.id === nextAgent.id);
        if (index >= 0) {
            agents[index] = nextAgent;
        } else {
            agents.unshift(nextAgent);
        }
        this._writeBuiltAgents(agents);
    }

    _sandboxUrl(sandbox, view) {
        const baseUrl = normalizeSandboxUrlForClient(sandbox.baseUrl || sandbox.sandboxUrl || '').replace(/\/$/, '');
        const dashboardUrl = normalizeSandboxUrlForClient(sandbox.dashboardUrl || '');
        const vncUrl = normalizeSandboxUrlForClient(sandbox.vncUrl || '');
        if (view === 'dashboard') return dashboardUrl || (baseUrl ? `${baseUrl}/index.html` : '');
        if (view === 'code') return baseUrl ? `${baseUrl}/code-server/` : '';
        if (view === 'jupyter') return baseUrl ? `${baseUrl}/jupyter` : '';
        return vncUrl || dashboardUrl || (baseUrl ? `${baseUrl}/index.html` : '');
    }

    _renderSandboxPanel() {
        if (!this.refs.sandboxPanel) return;
        const entries = this._sandboxEntries(this.state.selectedAgent);
        this.refs.sandboxPanel.innerHTML = '';

        if (!this.state.selectedAgent) {
            this.refs.sandboxPanel.appendChild(el('p', { className: 'ac-sandbox-empty', text: 'Select a built agent in My Agent first.' }));
            return;
        }
        if (this.state.sandboxLoading) {
            this.refs.sandboxPanel.appendChild(el('p', { className: 'ac-sandbox-empty', text: 'Connecting to Orchestrator for sandbox info…' }));
            return;
        }
        if (!entries.length) {
            this.refs.sandboxPanel.appendChild(el('p', {
                className: 'ac-sandbox-empty',
                text: this.state.sandboxError
                    ? `No sandbox available for this agent: ${this.state.sandboxError}`
                    : 'No sandbox available for this agent. Ensure Orchestrator is running and build_plan.json in this workspace includes MCP tools.',
            }));
            return;
        }

        const [agentName, sandbox] = this._selectedSandboxEntry();
        this.state.selectedSandboxAgent = agentName;
        const currentUrl = this._sandboxUrl(sandbox, this.state.sandboxView);

        this.refs.sandboxPanel.append(
            el('box', { className: 'ac-sandbox-meta' }, [
                el('strong', { text: agentName }),
                el('small', { text: normalizeSandboxUrlForClient(sandbox.baseUrl || sandbox.sandboxUrl || sandbox.dashboardUrl || '') }),
            ]),
            entries.length > 1 ? el('select', {
                className: 'ac-sandbox-select',
                onChange: (e) => {
                    this.state.selectedSandboxAgent = e.target.value;
                    this._renderSandboxPanel();
                },
            }, entries.map(([name]) => el('option', { attrs: { value: name, selected: name === agentName ? 'selected' : null }, text: name }))) : null,
            el('box', { className: 'ac-sandbox-tabs' }, [
                this._sandboxTab('vnc', 'Live desktop'),
                this._sandboxTab('dashboard', 'Home'),
                this._sandboxTab('code', 'VSCode'),
                this._sandboxTab('jupyter', 'Jupyter'),
            ]),
            currentUrl
                ? el('box', { className: `ac-sandbox-frame-wrap ac-sandbox-view-${this.state.sandboxView}` }, [
                    el('iframe', {
                        className: 'ac-sandbox-frame',
                        attrs: {
                            src: currentUrl,
                            title: `${agentName} sandbox`,
                            allow: 'clipboard-read; clipboard-write; fullscreen',
                        },
                    }),
                ])
                : el('p', { className: 'ac-sandbox-empty', text: 'This sandbox has no displayable URL.' }),
        );
    }

    _sandboxTab(view, label) {
        return el('button', {
            className: `ac-sandbox-tab${this.state.sandboxView === view ? ' is-active' : ''}`,
            type: 'button',
            onClick: () => {
                this.state.sandboxView = view;
                this._renderSandboxPanel();
            },
        }, label);
    }

    _setSidebar(open) {
        this.state.sidebarOpen = open;
        this.root.classList.toggle('sidebar-open', open);
        this.root.classList.toggle('sidebar-closed', !open);
    }

    _autoResizeInput(ta) {
        ta.style.height = 'auto';
        ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
    }

    _onInputKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this._sendMessage();
        }
    }

    _buildUserContent(text, attachments) {
        const parts = [text.trim()];
        attachments.forEach((a) => {
            if (a.kind === 'image') {
                parts.push(`[Image: ${a.name}]`);
            } else {
                parts.push(`[File: ${a.name} (${Math.round(a.size / 1024)} KB)]`);
            }
        });
        return parts.filter(Boolean).join('\n');
    }

    async _sendMessage() {
        if (this.state.sending) return;
        const text = this.refs.input.value.trim();
        const attachments = [...this.state.pendingAttachments];
        if (!text && !attachments.length) return;

        const content = this._buildUserContent(text, attachments);
        this.refs.input.value = '';
        this._autoResizeInput(this.refs.input);
        this.state.pendingAttachments = [];
        this._renderAttachments();

        store.appendMessage(this.state.conversationId, {
            role: 'user',
            content,
            attachments: attachments.map((a) => ({
                id: a.id,
                name: a.name,
                kind: a.kind,
                previewUrl: a.previewUrl,
            })),
        });

        const conv = store.getConversation(this.state.conversationId);
        this.refs.title.textContent = conv?.title || 'New chat';
        this._renderMessages();
        this._renderHistory();

        const typing = el('article', { className: 'ac-message is-assistant is-typing' }, [
            el('box', { className: 'ac-msg-avatar', text: 'AI' }),
            el('box', { className: 'ac-msg-body' }, el('box', { className: 'ac-typing-dots' }, '●●●')),
        ]);
        this.refs.messageList.appendChild(typing);
        this._scrollToBottom();

        this.state.sending = true;
        this.refs.sendBtn.disabled = true;
        this._setStatus('Thinking…');

        try {
            const history = store.toApiHistory(conv.messages.slice(0, -1));
            const response = await sendChat({
                userInput: content,
                history,
                workspace: this.state.selectedAgent?.workspace || '',
                agentId: this.state.selectedAgent?.id || '',
                bigSessionId: conv.bigSessionId || '',
                smallSessionId: conv.smallSessionId || '',
                userId: conv.userId || '',
            });
            const answer = (response && response.answer) || '';
            if (response && (response.big_session_id || response.small_session_id)) {
                store.updateConversation(this.state.conversationId, {
                    bigSessionId: response.big_session_id || conv.bigSessionId || null,
                    smallSessionId: response.small_session_id || null,
                    userId: response.user_id || conv.userId || null,
                    memoryMdPath: response.memory_md_path || null,
                });
            }
            store.appendMessage(this.state.conversationId, { role: 'assistant', content: answer });
            this._setStatus('');
        } catch (err) {
            store.appendMessage(this.state.conversationId, {
                role: 'assistant',
                content: `Sorry, the request failed: ${err.message || err}\n\nEnsure Orchestrator is running (default http://localhost:8001/chat) and a runnable Agent exists under backend/workspace.`,
            });
            this._setStatus('Send failed', true);
        } finally {
            this.state.sending = false;
            this.refs.sendBtn.disabled = false;
            this._renderMessages();
            this._renderHistory();
        }
    }

    _setStatus(text, isError) {
        this.refs.statusBar.textContent = text;
        this.refs.statusBar.classList.toggle('is-error', !!isError);
    }

    _scrollToBottom() {
        requestAnimationFrame(() => {
            const body = this.refs.main.querySelector('.ac-chat-body');
            if (body) body.scrollTop = body.scrollHeight;
        });
    }
}
