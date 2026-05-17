// Game bootstrap
import { init } from './game/index.js'
import { AgentChatApp } from './agent-chat/AgentChatApp.js'
import { BOX } from './agent-chat/dom.js'
import '../css/agent-chat.less'

init()
initAgentSwitcher()

function initAgentSwitcher() {
    const switchButton = document.createElement('button')
    switchButton.className = 'my-agent-switch'
    switchButton.type = 'button'
    switchButton.textContent = 'My Agent'
    document.body.appendChild(switchButton)

    let agentApp = null
    let agentMount = null
    let hiddenNodes = []

    switchButton.addEventListener('click', () => {
        if (agentApp) {
            agentApp.destroy()
            agentMount.remove()
            agentApp = null
            agentMount = null

            hiddenNodes.forEach((node) => {
                node.style.display = node.dataset.beforeAgentDisplay || ''
                delete node.dataset.beforeAgentDisplay
            })
            hiddenNodes = []
            document.body.classList.remove('agent-chat-body', 'agent-chat-embedded')
            switchButton.classList.remove('is-agent-view')
            switchButton.textContent = 'My Agent'
            return
        }

        hiddenNodes = Array.from(document.body.children).filter((node) => node !== switchButton)
        hiddenNodes.forEach((node) => {
            node.dataset.beforeAgentDisplay = node.style.display || ''
            node.style.display = 'none'
        })

        document.body.classList.add('agent-chat-body', 'agent-chat-embedded')
        agentMount = document.createElement(BOX)
        agentMount.id = 'agent-chat-app'
        document.body.appendChild(agentMount)
        agentApp = new AgentChatApp(agentMount)

        switchButton.classList.add('is-agent-view')
        switchButton.textContent = 'Back to game'
    })
}