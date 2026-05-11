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
        var activeFlowButton = null;
        var activePlatformButton = null;
        var activeToolButton = null;
        var selectedFlowId = null;

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
                game.renderFlowTemplate(template.id, null, getUserTask());
                showPlatformField();
                setActiveFlowButton(button);
                setActiveToolButton(null);
                updatePlatformCount(game.cubes.length);
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
                placementTip.innerHTML = getUserTask() ? '正在用你的任务演示流程' : '未输入任务，展示 Agent 角色流转';
            }
        });

        editorPanel.style.display = 'block';
        game.start();
        game.clearEditorScene();
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

        game.placementCompletedCallback = function () {
            setActiveToolButton(null);
        };

        editorPanel.addEventListener(game.mouse.down, function (event) {
            // Prevent canvas from entering jump-charge when clicking panel background
            if (event.target === editorPanel) {
                event.stopPropagation();
            }
        });

        // 失败后棋子回到当前平台继续尝试。
        game.failCallback = function () {
            game.returnToLastJumpPoint();
        };
    };
}

module.exports = {
    init
}