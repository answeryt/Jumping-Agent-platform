const Game = require('./game')

function init() {
    window.onload = function () {
        var game = new Game();

        var editorPanel = document.querySelector('.editor-panel');
        var taskInput = document.querySelector('.task-input');
        var playFlowBtn = document.querySelector('.play-flow');
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
        var activeFlowButton = null;
        var activePlatformButton = null;
        var activeToolButton = null;
        var selectedFlowId = null;
        var selectedSceneTarget = null;

        window.game = game;

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
                placementTip.innerHTML = '可选择平台样式后继续添加平台';
            }
        }

        function getUserTask() {
            return taskInput ? taskInput.value.trim() : '';
        }

        function updateFlowDemoTip(flowId) {
            if (!flowDemoTip) {
                return;
            }
            flowDemoTip.innerHTML = '演示时可拖动画布、缩放视角；流程会自动推进。';
        }

        function setPanelCollapsed(collapsed) {
            if (!editorPanel || !consoleToggleBtn) {
                return;
            }
            editorPanel.classList.toggle('collapsed', collapsed);
            consoleToggleBtn.innerHTML = collapsed ? '展开控制台' : '收回控制台';
            consoleToggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        }

        function closeSelectionMenu() {
            selectedSceneTarget = null;
            if (selectionMenu) {
                selectionMenu.classList.remove('visible');
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

            menuTitle.innerHTML = isPlatform ? '跳台操作' : '棋子操作';
            menuDeleteBtn.innerHTML = isPlatform ? '删除跳台' : '删除棋子';
            menuJumperSelectBtn.style.display = isPlatform ? 'inline-flex' : 'none';
            menuTaskInput.style.display = isPlatform ? 'block' : 'none';
            menuTaskSaveBtn.style.display = isPlatform ? 'inline-flex' : 'none';
            menuTaskInput.value = currentTask;
            menuTaskInput.placeholder = isPlatform ? '请输入这个跳台负责的任务' : '';

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
                game.placeJumperAt(selectedSceneTarget.platform, {
                    x: selectedSceneTarget.platform.position.x,
                    y: game.config.jumpHeight / 2,
                    z: selectedSceneTarget.platform.position.z
                });
                if (placementTip) {
                    placementTip.innerHTML = '已将棋子切换到当前跳台';
                }
                closeSelectionMenu();
            });
        }

        if (menuTaskSaveBtn) {
            menuTaskSaveBtn.addEventListener('pointerdown', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (!selectedSceneTarget || selectedSceneTarget.type !== 'platform') {
                    return;
                }
                game.updatePlatformTask(selectedSceneTarget.platform, menuTaskInput.value);
                if (placementTip) {
                    placementTip.innerHTML = menuTaskInput.value.trim() ? '已更新跳台负责任务' : '已清空跳台负责任务';
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
                    placementTip.innerHTML = '在画布中点击或拖动放置流程模板';
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
                    placementTip.innerHTML = '在画布中点击或拖动放置新平台';
                }
            });
            platformOptions.appendChild(button);
        });

        playFlowBtn.addEventListener('pointerdown', function (event) {
            event.preventDefault();
            event.stopPropagation();
            if (!selectedFlowId) {
                if (placementTip) {
                    placementTip.innerHTML = '请先选择一个流程模板';
                }
                return;
            }
            game.renderFlowTemplate(selectedFlowId, null, getUserTask());
            game.playFlowDemo(selectedFlowId, getUserTask());
            if (placementTip) {
                placementTip.innerHTML = getUserTask()
                    ? '正在用你的任务演示流程'
                    : '未输入任务，展示 Agent 角色流转';
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
                placementTip.innerHTML = '在画布中点击或拖动放置新平台';
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

        // 失败后棋子回到当前平台继续尝试。
        game.failCallback = function () {
            game.returnToLastJumpPoint();
        };
    };
}

module.exports = {
    init
}