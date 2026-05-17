'use strict';

import { AgentChatApp } from './AgentChatApp.js';
import { BOX } from './dom.js';
import '../../css/agent-chat.less';

/**
 * Agent chat entry: mounts DOM via JS without hand-written page HTML.
 */
function bootstrap() {
    document.documentElement.lang = 'en';
    document.title = document.title || 'Agent Chat';

    const mount = document.createElement(BOX);
    mount.id = 'agent-chat-app';
    document.body.appendChild(mount);
    document.body.classList.add('agent-chat-body');

    const app = new AgentChatApp(mount);
    if (typeof window !== 'undefined') {
        window.__agentChatApp = app;
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
} else {
    bootstrap();
}
