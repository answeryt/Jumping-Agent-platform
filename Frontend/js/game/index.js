const Game = require('./game')
const BuildClient = require('./buildClient')

function init() {
    window.onload = function () {
        var game = new Game();

        var editorPanel = document.querySelector('.editor-panel');
        var taskInput = document.querySelector('.task-input');
        var playFlowBtn = document.querySelector('.play-flow');
        var buildAgentBtn = document.querySelector('.build-agent');
        var buildStatusEl = document.querySelector('.build-status');
        var chooseAppBtn = document.querySelector('.choose-app');
        var appModal = document.querySelector('.app-modal');
        var appModalCloseBtn = document.querySelector('.app-modal-close');
        var wechatConnectStartBtn = document.querySelector('.wechat-connect-start');
        var wechatWorkspaceEl = document.querySelector('.wechat-workspace');
        var wechatQrPanel = document.querySelector('.wechat-qr-panel');
        var wechatQrImage = document.querySelector('.wechat-qr-image');
        var wechatQrLink = document.querySelector('.wechat-qr-link');
        var wechatStatus = document.querySelector('.wechat-status');
        var wechatAccountId = document.querySelector('.wechat-account-id');
        var wechatResult = document.querySelector('.wechat-result');
        var flowOptions = document.querySelector('.flow-options');
        var platformField = document.querySelector('.platform-field');
        var platformOptions = document.querySelector('.platform-options');
        var addPlatformBtn = document.querySelector('.add-platform');
        var addJumperBtn = document.querySelector('.add-jumper');
        var platformCountEl = document.querySelector('.platform-count');
        var placementTip = document.querySelector('.placement-tip');
        var flowDemoTip = document.querySelector('.flow-demo-tip');
        var consoleToggleBtn = document.querySelector('.panel-toggle');
        var selectionMenu = document.querySelector('.selection-menu');
        var menuTitle = document.querySelector('.selection-menu-title');
        var menuTaskInput = document.querySelector('.selection-task-input');
        var menuDeleteBtn = document.querySelector('.selection-delete');
        var menuJumperSelectBtn = document.querySelector('.selection-jumper-select');
        var menuTaskSaveBtn = document.querySelector('.selection-task-save');
        var menuToolsDoneBtn = document.querySelector('.selection-tools-done');
        var menuToolOptions = Array.prototype.slice.call(document.querySelectorAll('.selection-tool-option'));
        var activeFlowButton = null;
        var activePlatformButton = null;
        var activeToolButton = null;
        var selectedFlowId = null;
        var selectedSceneTarget = null;
        var pendingSelectedTools = [];
        var activeBuild = null;
        var latestBuiltAgent = null;
        var wechatPollingTimer = null;
        var currentWeixinSessionKey = '';

        window.game = game;
        setChooseAppEnabled(false);

        function updatePlatformCount(count) {
            if (platformCountEl) {
                platformCountEl.innerHTML = count;
            }
        }

        function setActiveFlowButton(button) {
            if (activeFlowButton) {
                activeFlowButton.classList.remove('active');
            }
            activeFlowButton = button;
            if (activeFlowButton) {
                activeFlowButton.classList.add('active');
            }
        }

        function setActivePlatformButton(button) {
            if (activePlatformButton) {
                activePlatformButton.classList.remove('active');
            }
            activePlatformButton = button;
            if (activePlatformButton) {
                activePlatformButton.classList.add('active');
            }
        }

        function setActiveToolButton(button) {
            if (activeToolButton) {
                activeToolButton.classList.remove('active');
            }
            activeToolButton = button;
            if (activeToolButton) {
                activeToolButton.classList.add('active');
            }
        }

        function showPlatformField() {
            if (platformField) {
                platformField.classList.add('visible');
            }
            if (addPlatformBtn) {
                addPlatformBtn.classList.add('visible');
            }
            if (placementTip) {
                placementTip.innerHTML = 'Choose a platform style, then add more platforms';
            }
        }

        function getUserTask() {
            return taskInput ? taskInput.value.trim() : '';
        }

        function updateFlowDemoTip(flowId) {
            if (!flowDemoTip) {
                return;
            }
            flowDemoTip.innerHTML = 'Drag the canvas and zoom during the demo; the flow advances automatically.';
        }

        function setPanelCollapsed(collapsed) {
            if (!editorPanel || !consoleToggleBtn) {
                return;
            }
            editorPanel.classList.toggle('collapsed', collapsed);
            consoleToggleBtn.innerHTML = collapsed ? 'Expand' : 'Collapse';
            consoleToggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        }

        function setBuildStatus(message, state) {
            if (!buildStatusEl) {
                return;
            }
            buildStatusEl.innerHTML = message || '';
            buildStatusEl.classList.remove('is-idle', 'is-running', 'is-error', 'is-success');
            buildStatusEl.classList.add('is-' + (state || 'idle'));
        }

        function setBuildBusy(isBusy) {
            if (buildAgentBtn) {
                buildAgentBtn.disabled = !!isBusy;
                buildAgentBtn.classList.toggle('is-running', !!isBusy);
                buildAgentBtn.innerHTML = isBusy ? 'Building...' : 'Build';
            }
        }

        function normalizeToolList(tools) {
            return Array.isArray(tools) ? tools.filter(Boolean) : [];
        }

        function setToolCardMode(enabled) {
            if (!selectionMenu) {
                return;
            }
            selectionMenu.classList.toggle('is-tool-selecting', !!enabled);
            if (menuTitle) {
                menuTitle.innerHTML = enabled ? 'Select tools' : (selectedSceneTarget && selectedSceneTarget.type === 'jumper' ? 'Jumper actions' : 'Platform actions');
            }
        }

        function renderToolOptions() {
            var selected = {};
            normalizeToolList(pendingSelectedTools).forEach(function (toolId) {
                selected[toolId] = true;
            });
            menuToolOptions.forEach(function (button) {
                button.classList.toggle('is-selected', !!selected[button.getAttribute('data-tool-id')]);
            });
        }

        function updateToolButtonLabel(platform) {
            if (!menuJumperSelectBtn) {
                return;
            }
            var tools = platform && platform.userData ? normalizeToolList(platform.userData.selectedTools) : [];
            menuJumperSelectBtn.innerHTML = tools.length ? 'Select tools (' + tools.length + ')' : 'Select tools';
        }

        function getPlatformToolMap() {
            var toolMap = {};
            for (var i = 0; i < game.cubes.length; i++) {
                var platform = game.cubes[i];
                var node = platform && platform.userData && platform.userData.flowNode;
                var tools = platform && platform.userData ? normalizeToolList(platform.userData.selectedTools) : [];
                if (node && node.id && tools.length) {
                    toolMap[node.id] = tools;
                }
            }
            return toolMap;
        }

        function getPlatformTaskMap() {
            var taskMap = {};
            for (var i = 0; i < game.cubes.length; i++) {
                var platform = game.cubes[i];
                var node = platform && platform.userData && platform.userData.flowNode;
                var task = platform && platform.userData ? (platform.userData.responsibleTask || '').trim() : '';
                if (node && node.id && task) {
                    taskMap[node.id] = task;
                }
            }
            return taskMap;
        }

        function getSelectedTemplate() {
            var templateId = selectedFlowId || game.selectedFlowTemplate;
            return game._getFlowTemplate(templateId);
        }

        function handleBuildEvent(message) {
            var payload = message.payload || {};
            if (message.type === 'build.stage') {
                setBuildStatus(payload.message || 'Backend is building...', 'running');
            } else if (message.type === 'agent.sandbox.created') {
                setBuildStatus('Sandbox created for ' + (payload.agentName || 'Agent'), 'running');
            } else if (message.type === 'agent.skeleton.created') {
                setBuildStatus('Skeleton generated for ' + (payload.agentName || 'Agent'), 'running');
            } else if (message.type === 'agent.codegen.started') {
                setBuildStatus('back_agent is refining ' + (payload.agentName || 'Agent'), 'running');
            } else if (message.type === 'agent.codegen.finished') {
                setBuildStatus((payload.agentName || 'Agent') + ' refined by back_agent', 'running');
            }
        }

        function saveBuiltAgent(payload, template, taskText) {
            var storageKey = 'agent_builder_built_agents_v1';
            var raw = localStorage.getItem(storageKey);
            var list = [];
            try {
                list = raw ? JSON.parse(raw) : [];
            } catch (error) {
                list = [];
            }
            if (!Array.isArray(list)) {
                list = [];
            }
            var agent = {
                id: 'built_' + Date.now(),
                name: (template && (template.title || template.name || template.id)) || 'My Agent',
                flowType: (template && (template.title || template.id)) || 'Unnamed flow',
                task: taskText || '',
                workspace: payload.workspace || '',
                sandboxes: payload.sandboxes || {},
                wechatPublicBaseUrl: payload.wechat_public_base_url || '',
                wechatWebhookUrl: payload.wechat_webhook_url || '',
                createdAt: Date.now()
            };
            list.unshift(agent);
            localStorage.setItem(storageKey, JSON.stringify(list.slice(0, 20)));
            return agent;
        }

        function getOrchestratorBaseUrl() {
            if (typeof window !== 'undefined' && window.AGENT_ORCHESTRATOR_BASE_URL) {
                return window.AGENT_ORCHESTRATOR_BASE_URL.replace(/\/$/, '');
            }
            if (typeof window === 'undefined' || !window.location || !window.location.hostname) {
                return 'http://localhost:8001';
            }
            return window.location.protocol + '//' + window.location.hostname + ':8001';
        }

        function setChooseAppEnabled(enabled) {
            if (!chooseAppBtn) {
                return;
            }
            chooseAppBtn.disabled = !enabled;
            chooseAppBtn.title = enabled ? 'Connect the built Agent to an app' : 'Build an Agent before choosing an app';
        }

        function setWechatResult(message, state) {
            if (!wechatResult) {
                return;
            }
            wechatResult.innerHTML = message || '';
            wechatResult.classList.remove('is-error', 'is-success', 'is-running');
            if (state) {
                wechatResult.classList.add('is-' + state);
            }
        }

        function setWechatStatus(message, state) {
            if (!wechatStatus) {
                return;
            }
            wechatStatus.innerHTML = message || '';
            wechatStatus.classList.remove('is-error', 'is-success', 'is-running');
            if (state) {
                wechatStatus.classList.add('is-' + state);
            }
        }

        function stopWechatPolling() {
            if (wechatPollingTimer) {
                window.clearInterval(wechatPollingTimer);
                wechatPollingTimer = null;
            }
        }

        function resetWechatConnectView() {
            stopWechatPolling();
            currentWeixinSessionKey = '';
            if (wechatConnectStartBtn) {
                wechatConnectStartBtn.disabled = false;
                wechatConnectStartBtn.innerHTML = 'Generate QR Code';
            }
            if (wechatQrPanel) {
                wechatQrPanel.classList.remove('visible');
            }
            if (wechatQrImage) {
                wechatQrImage.removeAttribute('src');
            }
            if (wechatQrLink) {
                wechatQrLink.href = '#';
                wechatQrLink.innerHTML = 'Open QR code link';
            }
            if (wechatAccountId) {
                wechatAccountId.innerHTML = '';
            }
            setWechatStatus('Use WeChat to scan the QR code and bind this Agent.', '');
            setWechatResult('', '');
        }

        function setAppModalOpen(open) {
            if (!appModal) {
                return;
            }
            appModal.classList.toggle('visible', !!open);
            appModal.setAttribute('aria-hidden', open ? 'false' : 'true');
            if (open) {
                resetWechatConnectView();
                if (wechatWorkspaceEl) {
                    wechatWorkspaceEl.innerHTML = latestBuiltAgent
                        ? 'Workspace: ' + latestBuiltAgent.workspace
                        : 'Build an Agent first.';
                }
                if (!latestBuiltAgent) {
                    setWechatResult('Build an Agent before connecting WeChat.', 'error');
                }
            } else {
                stopWechatPolling();
            }
        }

        function parseJsonResponse(response) {
            return response.text().then(function (text) {
                var data = {};
                try {
                    data = text ? JSON.parse(text) : {};
                } catch (error) {
                    data = {};
                }
                if (!response.ok) {
                    throw new Error((data.detail || text || 'Request failed'));
                }
                return data;
            });
        }

        function pollWechatLoginStatus() {
            if (!currentWeixinSessionKey) {
                return;
            }
            fetch(getOrchestratorBaseUrl() + '/weixin/login/status?sessionKey=' + encodeURIComponent(currentWeixinSessionKey))
                .then(parseJsonResponse)
                .then(function (data) {
                    if (data.status === 'connected') {
                        stopWechatPolling();
                        if (wechatConnectStartBtn) {
                            wechatConnectStartBtn.disabled = false;
                            wechatConnectStartBtn.innerHTML = 'Generate New QR Code';
                        }
                        if (wechatAccountId) {
                            wechatAccountId.innerHTML = 'Connected account: ' + (data.accountId || '');
                        }
                        setWechatStatus(data.message || 'WeChat connected. Send a message to this Agent in WeChat.', 'success');
                        setWechatResult('The Agent is now running for this WeChat account.', 'success');
                        setBuildStatus('WeChat connected: ' + (data.accountId || 'account'), 'success');
                    } else if (data.status === 'already_connected') {
                        stopWechatPolling();
                        if (wechatConnectStartBtn) {
                            wechatConnectStartBtn.disabled = false;
                            wechatConnectStartBtn.innerHTML = 'Generate New QR Code';
                        }
                        if (wechatAccountId && data.accountId) {
                            wechatAccountId.innerHTML = 'Connected account: ' + data.accountId;
                        }
                        setWechatStatus(data.message || 'WeChat is already connected. Current Agent is now running.', 'success');
                        setWechatResult('The current Agent is now running for this WeChat account.', 'success');
                    } else if (data.status === 'failed') {
                        stopWechatPolling();
                        if (wechatConnectStartBtn) {
                            wechatConnectStartBtn.disabled = false;
                            wechatConnectStartBtn.innerHTML = 'Retry QR Code';
                        }
                        setWechatStatus(data.message || 'WeChat connection failed.', 'error');
                        setWechatResult(data.message || 'WeChat connection failed.', 'error');
                    } else {
                        setWechatStatus(data.message || 'Waiting for WeChat scan confirmation...', 'running');
                    }
                })
                .catch(function (error) {
                    stopWechatPolling();
                    if (wechatConnectStartBtn) {
                        wechatConnectStartBtn.disabled = false;
                        wechatConnectStartBtn.innerHTML = 'Retry QR Code';
                    }
                    setWechatResult(error.message || 'Unable to check WeChat login status.', 'error');
                });
        }

        function startWechatLogin() {
            if (!latestBuiltAgent || !latestBuiltAgent.workspace) {
                setWechatResult('Build an Agent before connecting WeChat.', 'error');
                return;
            }
            stopWechatPolling();
            if (wechatConnectStartBtn) {
                wechatConnectStartBtn.disabled = true;
                wechatConnectStartBtn.innerHTML = 'Generating...';
            }
            setWechatStatus('Requesting WeChat QR code...', 'running');
            setWechatResult('', '');
            fetch(getOrchestratorBaseUrl() + '/weixin/login/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    workspace: latestBuiltAgent.workspace,
                    force: true
                })
            }).then(parseJsonResponse).then(function (data) {
                currentWeixinSessionKey = data.sessionKey || '';
                if (!data.qrcodeUrl || !currentWeixinSessionKey) {
                    throw new Error(data.message || 'Backend did not return a QR code.');
                }
                if (wechatQrImage) {
                    wechatQrImage.src = data.qrcodeUrl;
                }
                if (wechatQrLink) {
                    wechatQrLink.href = data.qrcodeUrl;
                    wechatQrLink.innerHTML = data.qrcodeUrl;
                }
                if (wechatQrPanel) {
                    wechatQrPanel.classList.add('visible');
                }
                if (wechatConnectStartBtn) {
                    wechatConnectStartBtn.disabled = false;
                    wechatConnectStartBtn.innerHTML = 'Refresh QR Code';
                }
                setWechatStatus(data.message || 'Scan this QR code with WeChat.', 'running');
                setWechatResult('Waiting for scan confirmation...', 'running');
                wechatPollingTimer = window.setInterval(pollWechatLoginStatus, 2000);
                pollWechatLoginStatus();
            }).catch(function (error) {
                if (wechatConnectStartBtn) {
                    wechatConnectStartBtn.disabled = false;
                    wechatConnectStartBtn.innerHTML = 'Retry QR Code';
                }
                setWechatStatus(error.message || 'Failed to generate QR code.', 'error');
                setWechatResult(error.message || 'Failed to generate QR code.', 'error');
            });
        }

        function closeSelectionMenu() {
            selectedSceneTarget = null;
            if (selectionMenu) {
                selectionMenu.classList.remove('visible');
                selectionMenu.classList.remove('is-tool-selecting');
                selectionMenu.style.left = '';
                selectionMenu.style.top = '';
                selectionMenu.style.right = '';
                selectionMenu.style.bottom = '';
            }
        }

        function openSelectionMenu(payload) {
            if (!selectionMenu || !menuTitle || !menuDeleteBtn || !menuJumperSelectBtn || !menuTaskInput || !menuTaskSaveBtn) {
                return;
            }
            if (!payload) {
                closeSelectionMenu();
                return;
            }

            selectedSceneTarget = payload;
            var isPlatform = payload.type === 'platform';
            var platform = payload.platform;
            var currentTask = isPlatform && platform && platform.userData ? (platform.userData.responsibleTask || '') : '';
            pendingSelectedTools = isPlatform && platform && platform.userData ? normalizeToolList(platform.userData.selectedTools).slice() : [];

            menuTitle.innerHTML = isPlatform ? 'Platform actions' : 'Jumper actions';
            menuDeleteBtn.innerHTML = isPlatform ? 'Delete platform' : 'Delete jumper';
            menuJumperSelectBtn.style.display = isPlatform ? 'inline-flex' : 'none';
            menuTaskInput.style.display = isPlatform ? 'block' : 'none';
            menuTaskSaveBtn.style.display = isPlatform ? 'inline-flex' : 'none';
            menuTaskInput.value = currentTask;
            menuTaskInput.placeholder = isPlatform ? 'Agent responsibility, e.g. business branch' : '';
            updateToolButtonLabel(platform);
            renderToolOptions();
            setToolCardMode(false);

            selectionMenu.classList.add('visible');

            var clientX = typeof payload.clientX === 'number' ? payload.clientX : window.innerWidth / 2;
            var clientY = typeof payload.clientY === 'number' ? payload.clientY : window.innerHeight / 2;
            var menuRect = selectionMenu.getBoundingClientRect();
            var menuWidth = menuRect.width || Math.min(320, window.innerWidth - 32);
            var menuHeight = menuRect.height || 220;
            var safeLeft = 16;
            var safeTop = 16;
            var maxLeft = Math.max(safeLeft, window.innerWidth - menuWidth - 16);
            var maxTop = Math.max(safeTop, window.innerHeight - menuHeight - 16);
            var desiredLeft = Math.min(Math.max(clientX - menuWidth / 2, safeLeft), maxLeft);
            var desiredTop = Math.min(Math.max(clientY - menuHeight - 12, safeTop), maxTop);

            selectionMenu.style.left = desiredLeft + 'px';
            selectionMenu.style.top = desiredTop + 'px';
            selectionMenu.style.right = 'auto';
            selectionMenu.style.bottom = 'auto';
        }

        if (consoleToggleBtn) {
            consoleToggleBtn.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                setPanelCollapsed(!editorPanel.classList.contains('collapsed'));
            });
        }

        if (buildAgentBtn) {
            buildAgentBtn.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (activeBuild && activeBuild.socket && activeBuild.socket.readyState === WebSocket.OPEN) {
                    setBuildStatus('A build is already in progress, please wait...', 'running');
                    return;
                }

                var template = getSelectedTemplate();
                if (!template) {
                    setBuildStatus('Please select a flow template first', 'error');
                    return;
                }

                setBuildBusy(true);
                setBuildStatus('Connecting to Orchestrator...', 'running');
                try {
                    activeBuild = BuildClient.connectAndBuild(template, getUserTask(), {
                        onStatus: function (message) {
                            setBuildStatus(message, 'running');
                        },
                        onEvent: handleBuildEvent,
                        onError: function (message) {
                            setBuildBusy(false);
                            setBuildStatus(message, 'error');
                            activeBuild = null;
                        },
                        onFinished: function (payload) {
                            setBuildBusy(false);
                            setBuildStatus(
                                payload.wechat_webhook_url
                                    ? 'Build complete. WeChat webhook ready: ' + payload.wechat_webhook_url
                                    : 'Build complete: ' + (payload.workspace || 'workspace generated'),
                                'success'
                            );
                            latestBuiltAgent = saveBuiltAgent(payload, template, getUserTask());
                            setChooseAppEnabled(!!(latestBuiltAgent && latestBuiltAgent.workspace));
                            activeBuild = null;
                        }
                    }, getPlatformToolMap(), getPlatformTaskMap());
                } catch (error) {
                    setBuildBusy(false);
                    setBuildStatus(error.message || 'Failed to start build', 'error');
                    activeBuild = null;
                }
            });
        }

        if (chooseAppBtn) {
            chooseAppBtn.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (!latestBuiltAgent || !latestBuiltAgent.workspace) {
                    setBuildStatus('Build an Agent before choosing an app', 'error');
                    return;
                }
                setAppModalOpen(true);
            });
        }

        if (appModalCloseBtn) {
            appModalCloseBtn.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                setAppModalOpen(false);
            });
        }

        if (appModal) {
            appModal.addEventListener('pointerdown', function (event) {
                if (event.target === appModal) {
                    event.preventDefault();
                    setAppModalOpen(false);
                }
            });
        }

        if (wechatConnectStartBtn) {
            wechatConnectStartBtn.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                startWechatLogin();
            });
        }

        if (menuDeleteBtn) {
            menuDeleteBtn.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (!selectedSceneTarget) {
                    return;
                }
                if (selectedSceneTarget.type === 'platform') {
                    game.removePlatform(selectedSceneTarget.platform);
                } else if (selectedSceneTarget.type === 'jumper') {
                    game.removeJumper(selectedSceneTarget.jumper);
                }
                closeSelectionMenu();
            });
        }

        if (menuJumperSelectBtn) {
            menuJumperSelectBtn.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (!selectedSceneTarget || selectedSceneTarget.type !== 'platform') {
                    return;
                }
                pendingSelectedTools = normalizeToolList(selectedSceneTarget.platform.userData.selectedTools).slice();
                renderToolOptions();
                setToolCardMode(true);
            });
        }

        if (menuToolsDoneBtn) {
            menuToolsDoneBtn.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (!selectedSceneTarget || selectedSceneTarget.type !== 'platform') {
                    setToolCardMode(false);
                    return;
                }
                game.updatePlatformTools(selectedSceneTarget.platform, pendingSelectedTools);
                updateToolButtonLabel(selectedSceneTarget.platform);
                if (placementTip) {
                    placementTip.innerHTML = pendingSelectedTools.length
                        ? 'Selected ' + pendingSelectedTools.length + ' backend tool(s)'
                        : 'Cleared backend tool selection';
                }
                setToolCardMode(false);
            });
        }

        menuToolOptions.forEach(function (button) {
            button.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                var toolId = button.getAttribute('data-tool-id');
                if (!toolId) {
                    return;
                }
                var index = pendingSelectedTools.indexOf(toolId);
                if (index === -1) {
                    pendingSelectedTools.push(toolId);
                } else {
                    pendingSelectedTools.splice(index, 1);
                }
                renderToolOptions();
            });
        });

        if (menuTaskSaveBtn) {
            menuTaskSaveBtn.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (!selectedSceneTarget || selectedSceneTarget.type !== 'platform') {
                    return;
                }
                game.updatePlatformTask(selectedSceneTarget.platform, menuTaskInput.value);
                if (placementTip) {
                    placementTip.innerHTML = menuTaskInput.value.trim() ? 'Platform responsibility updated' : 'Platform responsibility cleared';
                }
                closeSelectionMenu();
            });
        }

        document.addEventListener('pointerdown', function (event) {
            if (!selectionMenu || !selectionMenu.classList.contains('visible')) {
                return;
            }
            if (selectionMenu.contains(event.target)) {
                return;
            }
            if (event.target === game.canvas) {
                return;
            }
            closeSelectionMenu();
        });

        game.getFlowTemplateList().forEach(function (template) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'flow-option';
            button.value = template.id;
            button.title = template.description;
            button.innerHTML = template.name;
            button.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                selectedFlowId = template.id;
                updateFlowDemoTip(template.id);
                game.beginFlowTemplatePlacement(template.id, game.selectedPlatformModel, getUserTask(), event);
                showPlatformField();
                setActiveFlowButton(button);
                setActiveToolButton(button);
                updatePlatformCount(game.cubes.length);
                if (placementTip) {
                    placementTip.innerHTML = 'Click or drag on the canvas to place the flow template';
                }
            });
            flowOptions.appendChild(button);
        });

        game.getPlatformModelList().forEach(function (modelId) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'platform-option';
            button.value = modelId;
            button.innerHTML = modelId;
            button.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                game.setSelectedPlatformModel(modelId);
                if (!selectedFlowId) {
                    showPlatformField();
                }
                setActivePlatformButton(button);
                setActiveToolButton(null);
                game.beginPlatformPlacement(modelId, event);
                if (placementTip) {
                    placementTip.innerHTML = 'Click or drag on the canvas to place a new platform';
                }
            });
            platformOptions.appendChild(button);
        });

        playFlowBtn.addEventListener('pointerdown', function (event) {
            event.preventDefault();
            event.stopPropagation();
            if (!selectedFlowId) {
                if (placementTip) {
                    placementTip.innerHTML = 'Please select a flow template first';
                }
                return;
            }
            game.renderFlowTemplate(selectedFlowId, null, getUserTask());
            game.playFlowDemo(selectedFlowId, getUserTask());
            if (placementTip) {
                placementTip.innerHTML = getUserTask()
                    ? 'Demoing the flow with your task'
                    : 'No task entered; showing agent role handoffs';
            }
            updateFlowDemoTip(selectedFlowId);
        });

        editorPanel.style.display = 'block';
        game.start();
        updatePlatformCount(game.cubes.length);

        addPlatformBtn.addEventListener('pointerdown', function (event) {
            event.preventDefault();
            event.stopPropagation();
            showPlatformField();
            game.beginPlatformPlacement(game.selectedPlatformModel, event);
            setActiveToolButton(addPlatformBtn);
            if (placementTip) {
                placementTip.innerHTML = 'Click or drag on the canvas to place a new platform';
            }
        });

        addJumperBtn.addEventListener('pointerdown', function (event) {
            event.preventDefault();
            event.stopPropagation();
            game.beginJumperPlacement(event);
            setActiveToolButton(addJumperBtn);
        });

        game.platformAddedCallback = function (count) {
            updatePlatformCount(count);
            setActiveToolButton(null);
        };

        game.platformMenuCallback = function (payload) {
            openSelectionMenu(payload);
        };

        game.placementCompletedCallback = function () {
            setActiveToolButton(null);
        };

        editorPanel.addEventListener(game.mouse.down, function (event) {
            // Prevent canvas from entering jump-charge when clicking panel background
            if (event.target === editorPanel) {
                event.stopPropagation();
            }
        });

        setPanelCollapsed(false);
        updateFlowDemoTip(selectedFlowId);

        // On failure, return the jumper to the current platform to retry.
        game.failCallback = function () {
            game.returnToLastJumpPoint();
        };
    };
}

module.exports = {
    init
}