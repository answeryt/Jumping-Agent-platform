const THREE = require('three')
const ModelConfig = require('./modelConfig')
const Tween = new (require('../lib/Tween'))()
const AudioManager = require('./audioManager')
const FlowTemplates = require('./flowTemplates')
const ThreeObjMtlLoader = require('three-obj-mtl-loader')
const OBJLoader = ThreeObjMtlLoader.OBJLoader
const MTLLoader = ThreeObjMtlLoader.MTLLoader

function Game() {
    this.scene = new THREE.Scene();
    this.viewGroup = new THREE.Group();
    this.group = new THREE.Group();
    this.viewGroup.add(this.group);
    this.scene.add(this.viewGroup);

    this.camera = new THREE.OrthographicCamera(
        window.innerWidth / -60,
        window.innerWidth / 60,
        window.innerHeight / 60,
        window.innerHeight / -60,
        0.1, 5000);
    this.camera.position.set(100, 100, 100);
    this.camera.lookAt(new THREE.Vector3(0, 0, 0))
    this.cameraPos = {
        current: new THREE.Vector3(0, 0, 0), // 摄像机当前的坐标
        next: new THREE.Vector3() // 摄像机即将要移到的位置
    };
    this.cameraSpeed = {
        x: 0,
        y: 0,
        z: 0
    }
    this.CAMERA_MOVE_TIME = 40;

    this.groupPos = {
        current: null,
        next: null
    }

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.shadowMap.enabled = true;
    this.renderer.antialias = true;
    document.body.appendChild(this.renderer.domElement);
    this.canvas = this.renderer.domElement;

    // 灯光
    var directionalLight = new THREE.DirectionalLight(0xffffff, 0.4);
    directionalLight.position.set(2, 5, -2);
    directionalLight.castShadow = true;
    directionalLight.shadow.camera.near = 0; //产生阴影的最近距离
    directionalLight.shadow.camera.far = 100; //产生阴影的最远距离
    let d = 15;
    directionalLight.shadow.camera.left = -d; //产生阴影距离位置的最左边位置
    directionalLight.shadow.camera.right = d; //最右边
    directionalLight.shadow.camera.top = d; //最上边
    directionalLight.shadow.camera.bottom = -d; //最下面
    directionalLight.shadow.mapSize.width = 2048;
    directionalLight.shadow.mapSize.height = 2048;
    this.scene.add(directionalLight);
    var ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    this.scene.add(ambientLight);

    this.config = {
        // 弹跳体参数设置
        jumpTopRadius: 0.3,
        jumpBottomRadius: 0.5,
        jumpHeight: 2,
        jumpColor: 0xffffff,
        // 立方体参数设置
        cubeX: 4,
        cubeY: 2,
        cubeZ: 4,
        cubeColor: 0x00ffff,
        // 圆柱体参数设置
        cylinderRadius: 2,
        cylinderHeight: 2,
        cylinderColor: 0x00ff00,
        // 设置缓存数组最大缓存多少个图形
        cubeMaxLen: 6,
        // 立方体内边缘之间的最小距离和最大距离
        cubeMinDis: 2,
        cubeMaxDis: 5,

        // 模型Config
        modelConfig:  new ModelConfig(),
    };

    this.mouse = {
        down: window.PointerEvent ? 'pointerdown' : (this.isPC() ? 'mousedown' : 'touchstart'),
        up: window.PointerEvent ? 'pointerup' : (this.isPC() ? 'mouseup' : 'touchend')
    };

    this.cubes = [];
    this.models = [];
    window.models=this.models;
    this.jumpers = [];
    this.flowBubbles = [];
    this.flowNodeMap = {};
    this.flowJumperMap = {};
    this.flowDemoToken = 0;
    this.jumper = null;
    this.currentCube = null;
    this.targetCube = null;
    this.raycaster = new THREE.Raycaster();
    this.pointerVector = new THREE.Vector2();
    this.selectedFlowTemplate = FlowTemplates[0].id;
    this.selectedPlatformModel = 'pingtai1';
    this.platformGap = 4;
    this.initialTargetOffset = { x: 8, z: 0 };
    this.placement = {
        type: null,
        modelId: null,
        preview: null,
        pointerId: null,
        targetPlatform: null,
        lastPosition: null
    };
    this._windowCleanup = null;
    this.activePointers = {};
    this.gesture = {
        mode: 'idle',
        primaryId: null,
        startX: 0,
        startY: 0,
        lastX: 0,
        lastY: 0,
        chargeTimer: null,
        pinchStartDistance: 0,
        pinchStartZoom: 1,
        pinchLastCenter: null
    };
    this.viewControl = {
        zoom: 1,
        minZoom: 0.2,
        maxZoom: 8,
        dragThreshold: 8,
        touchChargeDelay: 80
    };

    // mousedown : -1
    // mouseup : 1
    this.JUMP_FRAME_NUM = 30;
    this.ADDSPEED = 0.0022;
    this.CHARGE_DISTANCE_PER_FRAME = 0.28;
    this.accelerate = {
        x: 0,       //水平匀速运动
        y: 0.044,   //固定值
        z: 0        //水平匀速运动
    }
    this.speed = {
        x: 0,       //向前进方向的速度 随着mousedown时间增加
        y: this.accelerate.y * this.JUMP_FRAME_NUM / 2,    //弹起的速度 固定值
        z: 0        //补偿速度 使jumper落在下一方块的中心轴上
    };
    this.jumpVelocity = {
        x: 0,
        z: 0
    };
    this.jumpChargePower = 0;
    this.jumpChargeDistance = 0;
    this.jumpPressFrame = 0;
    this.mouseState = 0;
    this.currentFrame = -1;
    this.score = 0;
    this.failAnimationToken = 0;
    this.panRightVector = new THREE.Vector3();
    this.panUpVector = new THREE.Vector3();

    this.failCallback = function () { };
    this.platformAddedCallback = function () { };
    this.placementCompletedCallback = function () { };

    this.audioManager = new AudioManager();
    //console test
    window.jumpers = this.jumpers;
    window.jumper = this.jumper;
    window.models = this.models;
    window.camera = this.camera;
    window.cameraPos = this.cameraPos;
    window.group = this.group;
}

Game.prototype.constructor = Game;

Object.assign(Game.prototype, {

    getPlatformModelList: function () {
        return this.config.modelConfig.objList.slice();
    },

    getFlowTemplateList: function () {
        return FlowTemplates.slice();
    },

    setSelectedFlowTemplate: function (templateId) {
        if (this._getFlowTemplate(templateId)) {
            this.selectedFlowTemplate = templateId;
        }
    },

    setSelectedPlatformModel: function (modelId) {
        if (this.config.modelConfig.objList.indexOf(modelId) !== -1) {
            this.selectedPlatformModel = modelId;
        }
    },

    _getFlowTemplate: function (templateId) {
        for (var i = 0; i < FlowTemplates.length; i++) {
            if (FlowTemplates[i].id === templateId) {
                return FlowTemplates[i];
            }
        }
        return null;
    },

    renderFlowTemplate: function (templateId, platformModel, userTask) {
        var template = this._getFlowTemplate(templateId || this.selectedFlowTemplate);
        if (!template) {
            return;
        }
        this.setSelectedFlowTemplate(template.id);
        if (platformModel) {
            this.setSelectedPlatformModel(platformModel);
        }

        this.clearEditorScene();
        this.group.position.x = 0;
        this.group.position.z = 0;

        var nodeMap = {};
        var jumperMap = {};
        var modelId = platformModel || this.selectedPlatformModel;
        for (var i = 0; i < template.nodes.length; i++) {
            var node = template.nodes[i];
            var platform = this.createPlatform({
                position: { x: node.x, y: 0, z: node.z },
                modelId: modelId
            });
            platform.userData.flowNode = node;
            nodeMap[node.id] = platform;

            var jumper = this.createJumper({
                position: {
                    x: node.x,
                    y: this.config.jumpHeight / 2,
                    z: node.z
                },
                color: this._getAgentColor(node.role),
                setActive: i === 0
            });
            jumper.userData.flowRole = node.role;
            jumper.userData.flowNodeId = node.id;
            jumperMap[node.id] = jumper;
            this._createFlowBubble(jumper, this._getInitialBubbleText(template, node, i, userTask));
        }

        this.flowNodeMap = nodeMap;
        this.flowJumperMap = jumperMap;
        this.currentCube = this.cubes[0] || null;
        this.targetCube = this.cubes[1] || null;
        this._fitFlowView();
        this.platformAddedCallback(this.cubes.length);
        this._render();
    },

    clearEditorScene: function () {
        this.flowDemoToken += 1;
        this.cancelPlacement();
        this._clearFlowBubbles();

        for (var i = 0; i < this.cubes.length; i++) {
            this.group.remove(this.cubes[i]);
            this._disposeObject(this.cubes[i]);
        }
        this.cubes.length = 0;

        for (var j = 0; j < this.models.length; j++) {
            this.removeModel(this.models[j]);
        }
        this.models.length = 0;

        for (var k = 0; k < this.jumpers.length; k++) {
            this.group.remove(this.jumpers[k]);
            this._disposeObject(this.jumpers[k]);
        }
        this.jumpers.length = 0;

        this.flowNodeMap = {};
        this.flowJumperMap = {};
        this.jumper = null;
        window.jumper = this.jumper;
        this.currentCube = null;
        this.targetCube = null;
        this.mouseState = 0;
        this.score = 0;
    },

    playFlowDemo: function (templateId, userTask) {
        var template = this._getFlowTemplate(templateId || this.selectedFlowTemplate);
        if (!template) {
            return;
        }
        var taskText = (userTask || '').trim();
        var token = ++this.flowDemoToken;

        if (template.visualMode === 'debate_round') {
            this._playDebateDemo(template, taskText, token);
        } else if (template.visualMode === 'parallel_fanout') {
            this._playParallelDemo(template, taskText, token);
        } else if (template.visualMode === 'hierarchical_delegate') {
            this._playHierarchicalDemo(template, taskText, token);
        } else if (template.visualMode === 'supervisor_dispatch') {
            this._playSupervisorDemo(template, taskText, token);
        } else {
            this._playLinearJumpDemo(template, taskText, token);
        }
    },

    _getAgentColor: function (role) {
        var colors = {
            dispatcher: 0xffb84d,
            worker: 0x58a6ff,
            aggregator: 0x7ee787,
            executor: 0xd2a8ff,
            evaluator: 0xff7b72,
            participant: 0xf2cc60,
            moderator: 0x79c0ff,
            manager: 0xff9bce,
            agent: 0xffffff
        };
        return colors[role] || colors.agent;
    },

    _getTemplateNode: function (template, nodeId) {
        for (var i = 0; i < template.nodes.length; i++) {
            if (template.nodes[i].id === nodeId) {
                return template.nodes[i];
            }
        }
        return null;
    },

    _getInitialBubbleText: function (template, node, index, userTask) {
        if (index === 0) {
            return 'what next';
        }
        if ((userTask || '').trim()) {
            return this._getDialogText(template, node, userTask);
        }
        return node.label || node.role || 'Agent';
    },

    _getDialogText: function (template, node, userTask) {
        var taskText = (userTask || '').trim();
        var dialog = template.dialogues && template.dialogues[node.id];
        if (dialog === 'what next') {
            return dialog;
        }
        if (!taskText) {
            return node.label || node.role || 'Agent';
        }
        if (typeof dialog === 'function') {
            return dialog(taskText);
        }
        return dialog || ((node.label || node.role || 'Agent') + ' 处理：' + taskText);
    },

    _playLinearJumpDemo: function (template, taskText, token) {
        var sequence = template.jumpSequence || [];
        var actions = [];
        for (var i = 0; i < sequence.length; i++) {
            actions.push({ type: 'say', node: sequence[i] });
            if (sequence[i + 1]) {
                actions.push({ type: 'jump', from: sequence[i], to: sequence[i + 1] });
            }
        }
        this._runDemoActions(template, actions, taskText, token);
    },

    _playDebateDemo: function (template, taskText, token) {
        var actions = [
            {
                type: 'sayText',
                node: template.moderator,
                text: taskText ? ('本轮议题：' + taskText) : '等待用户输入议题'
            }
        ];
        for (var i = 0; i < template.participants.length; i++) {
            actions.push({ type: 'say', node: template.participants[i] });
            actions.push({ type: 'pulse', node: template.participants[i] });
        }
        actions.push({ type: 'say', node: template.moderator });
        actions.push({ type: 'pulse', node: template.moderator, subtle: true });
        this._runDemoActions(template, actions, taskText, token);
    },

    _playParallelDemo: function (template, taskText, token) {
        var actions = [
            { type: 'say', node: template.dispatcher },
            { type: 'pulse', node: template.dispatcher, subtle: true }
        ];
        for (var i = 0; i < template.workers.length; i++) {
            actions.push({ type: 'say', node: template.workers[i] });
            actions.push({ type: 'pulse', node: template.workers[i] });
            actions.push({ type: 'jump', from: template.workers[i], to: template.aggregator });
        }
        actions.push({ type: 'say', node: template.aggregator });
        actions.push({ type: 'pulse', node: template.aggregator, subtle: true });
        this._runDemoActions(template, actions, taskText, token);
    },

    _playHierarchicalDemo: function (template, taskText, token) {
        var actions = [
            { type: 'say', node: template.manager },
            { type: 'pulse', node: template.manager, subtle: true }
        ];
        for (var i = 0; i < template.workers.length; i++) {
            actions.push({ type: 'say', node: template.workers[i] });
            actions.push({ type: 'jump', from: template.workers[i], to: template.final });
            actions.push({ type: 'say', node: template.manager });
        }
        actions.push({ type: 'say', node: template.final });
        this._runDemoActions(template, actions, taskText, token);
    },

    _playSupervisorDemo: function (template, taskText, token) {
        var actions = [
            { type: 'say', node: template.supervisor },
            { type: 'pulse', node: template.supervisor, subtle: true }
        ];
        for (var i = 0; i < template.agents.length; i++) {
            actions.push({ type: 'say', node: template.agents[i] });
            actions.push({ type: 'jump', from: template.agents[i], to: template.supervisor });
            actions.push({ type: 'say', node: template.supervisor });
        }
        this._runDemoActions(template, actions, taskText, token);
    },

    _runDemoActions: function (template, actions, taskText, token) {
        var self = this;
        var index = 0;

        function next() {
            if (token !== self.flowDemoToken || index >= actions.length) {
                return;
            }
            var action = actions[index++];
            if (action.type === 'say' || action.type === 'sayText') {
                var sayJumper = self.flowJumperMap[action.node];
                var node = self._getTemplateNode(template, action.node);
                if (sayJumper && node) {
                    self._setFlowBubbleText(
                        sayJumper,
                        action.text || self._getDialogText(template, node, taskText)
                    );
                }
                window.setTimeout(next, 760);
            } else if (action.type === 'pulse') {
                self._animateAgentPulse(self.flowJumperMap[action.node], function () {
                    window.setTimeout(next, 260);
                }, token, action.subtle);
            } else if (action.type === 'jump') {
                self._animateDemoJump(
                    self.flowJumperMap[action.from],
                    self.flowNodeMap[action.to],
                    function () {
                        window.setTimeout(next, 360);
                    },
                    token
                );
            } else {
                window.setTimeout(next, 300);
            }
        }

        next();
    },

    _createFlowBubble: function (jumper, text) {
        var el = document.createElement('div');
        el.className = 'flow-bubble';
        el.textContent = text;
        document.body.appendChild(el);
        this.flowBubbles.push({
            jumper: jumper,
            el: el
        });
        this._updateFlowBubbles();
        return el;
    },

    _setFlowBubbleText: function (jumper, text) {
        for (var i = 0; i < this.flowBubbles.length; i++) {
            if (this.flowBubbles[i].jumper === jumper) {
                this.flowBubbles[i].el.textContent = text;
                return;
            }
        }
    },

    _clearFlowBubbles: function () {
        for (var i = 0; i < this.flowBubbles.length; i++) {
            if (this.flowBubbles[i].el.parentNode) {
                this.flowBubbles[i].el.parentNode.removeChild(this.flowBubbles[i].el);
            }
        }
        this.flowBubbles.length = 0;
    },

    _updateFlowBubbles: function () {
        var width = window.innerWidth;
        var height = window.innerHeight;
        var position = new THREE.Vector3();
        for (var i = 0; i < this.flowBubbles.length; i++) {
            var item = this.flowBubbles[i];
            if (!item.jumper || !item.el) {
                continue;
            }
            position.set(0, this.config.jumpHeight + 2.4, 0);
            item.jumper.localToWorld(position);
            position.project(this.camera);
            item.el.style.left = ((position.x + 1) / 2 * width) + 'px';
            item.el.style.top = ((-position.y + 1) / 2 * height) + 'px';
            item.el.style.display = position.z < 1 ? 'block' : 'none';
        }
    },

    _animateDemoJump: function (jumper, targetPlatform, done, token) {
        if (!jumper || !targetPlatform) {
            if (done) done();
            return;
        }
        var start = {
            x: jumper.position.x,
            y: jumper.position.y,
            z: jumper.position.z
        };
        var end = {
            x: targetPlatform.position.x,
            y: this.config.jumpHeight / 2,
            z: targetPlatform.position.z
        };
        var frame = 0;
        var total = 36;
        var arcHeight = 5;
        var self = this;

        function step() {
            if (token !== self.flowDemoToken) {
                return;
            }
            frame += 1;
            var t = Math.min(frame / total, 1);
            var eased = Tween.Sine.easeInOut(t, 0, 1, 1);
            jumper.position.x = start.x + (end.x - start.x) * eased;
            jumper.position.z = start.z + (end.z - start.z) * eased;
            jumper.position.y = start.y + (end.y - start.y) * eased + Math.sin(Math.PI * t) * arcHeight;
            jumper.rotation.z = -Math.PI * 2 * t;
            self._render();
            if (t < 1) {
                requestAnimationFrame(step);
            } else {
                jumper.position.set(end.x, end.y, end.z);
                jumper.rotation.z = 0;
                self._render();
                if (done) done();
            }
        }

        step();
    },

    _animateAgentPulse: function (jumper, done, token, subtle) {
        if (!jumper) {
            if (done) done();
            return;
        }
        var startY = jumper.position.y;
        var baseScale = {
            x: jumper.scale.x,
            y: jumper.scale.y,
            z: jumper.scale.z
        };
        var frame = 0;
        var total = subtle ? 18 : 26;
        var lift = subtle ? 0.45 : 1.2;
        var self = this;

        function step() {
            if (token !== self.flowDemoToken) {
                return;
            }
            frame += 1;
            var t = Math.min(frame / total, 1);
            var wave = Math.sin(Math.PI * t);
            jumper.position.y = startY + wave * lift;
            jumper.scale.x = baseScale.x + wave * 0.12;
            jumper.scale.z = baseScale.z + wave * 0.12;
            self._render();
            if (t < 1) {
                requestAnimationFrame(step);
            } else {
                jumper.position.y = startY;
                jumper.scale.set(baseScale.x, baseScale.y, baseScale.z);
                self._render();
                if (done) done();
            }
        }

        step();
    },

    _fitFlowView: function () {
        this.cameraPos.current = new THREE.Vector3(0, 0, 0);
        this.cameraPos.next = new THREE.Vector3(0, 0, 0);
        this.camera.lookAt(this.cameraPos.current);
    },

    createPlatform: function (options) {
        options = options || {};
        var cubeType = options.shape || 'cube';
        var position = options.position || { x: 0, y: 0, z: 0 };
        var modelId = options.modelId || this.selectedPlatformModel;
        var geometry = cubeType === 'cube' ?
            new THREE.CubeGeometry(this.config.cubeX, this.config.cubeY, this.config.cubeZ) :
            new THREE.CylinderGeometry(this.config.cylinderRadius, this.config.cylinderRadius, this.config.cylinderHeight, 100);
        var material = new THREE.MeshLambertMaterial({
            color: 0xffffff,
            transparent: true,
            opacity: 0
        });
        var mesh = new THREE.Mesh(geometry, material);

        mesh.position.set(position.x, position.y, position.z);
        this.createModel(position, modelId, mesh);
        this.testPosition(mesh.position);
        this.cubes.push(mesh);
        this.group.add(mesh);
        this._render();

        if (!this.currentCube) {
            this.currentCube = mesh;
        } else if (!this.targetCube) {
            this.targetCube = mesh;
        }

        this.camera.lookAt(this.cameraPos.current);
        this.platformAddedCallback(this.cubes.length);
        return mesh;
    },

    addUserPlatform: function (direction, modelId) {
        var from = this.cubes[this.cubes.length - 1] || this.currentCube;
        if (!from) {
            return this.createPlatform({
                position: { x: 0, y: 0, z: 0 },
                modelId: modelId || this.selectedPlatformModel
            });
        }

        var position = {
            x: from.position.x,
            y: from.position.y,
            z: from.position.z
        };
        if (direction === 'z') {
            position.z -= this.config.cubeZ + this.platformGap;
        } else {
            position.x += this.config.cubeX + this.platformGap;
        }

        return this.createPlatform({
            position: position,
            modelId: modelId || this.selectedPlatformModel
        });
    },

    beginPlatformPlacement: function (modelId, startEvent) {
        this.cancelPlacement();
        this.placement.type = 'platform';
        this.placement.modelId = modelId || this.selectedPlatformModel;
        if (startEvent) {
            this._startWindowPlacementDrag(startEvent);
        }
    },

    beginJumperPlacement: function (startEvent) {
        this.cancelPlacement();
        this.placement.type = 'jumper';
        this.placement.modelId = null;
        if (startEvent) {
            this._startWindowPlacementDrag(startEvent);
        }
    },

    _startWindowPlacementDrag: function (event) {
        if (this._windowCleanup) {
            this._windowCleanup();
        }
        var self = this;
        var pid = event.pointerId;
        this.placement.pointerId = pid;

        function onMove(e) {
            if (e.pointerId !== pid) return;
            self._updatePlacementPreview(e);
        }
        function onUp(e) {
            if (e.pointerId !== pid) return;
            remove();
            if (self.placement.lastPosition) {
                self._commitPlacementDrag();
            }
            // no lastPosition → keep placement.type active, wait for canvas click
        }
        function onCancel(e) {
            if (e.pointerId !== pid) return;
            remove();
            self.cancelPlacement();
        }
        function remove() {
            window.removeEventListener('pointermove', onMove);
            window.removeEventListener('pointerup', onUp);
            window.removeEventListener('pointercancel', onCancel);
            self._windowCleanup = null;
        }
        this._windowCleanup = remove;
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
        window.addEventListener('pointercancel', onCancel);
        this._updatePlacementPreview(event);
    },

    cancelPlacement: function () {
        if (this._windowCleanup) {
            this._windowCleanup();
        }
        this._clearPlacementPreview();
        this.placement.type = null;
        this.placement.modelId = null;
        this.placement.pointerId = null;
        this.placement.targetPlatform = null;
        this.placement.lastPosition = null;
        this._render();
    },

    _isPointerOverCanvas: function (event) {
        var rect = this.canvas.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right ||
            event.clientY < rect.top || event.clientY > rect.bottom) {
            return false;
        }
        var panel = document.querySelector('.editor-panel');
        if (panel) {
            var pr = panel.getBoundingClientRect();
            if (event.clientX >= pr.left && event.clientX <= pr.right &&
                event.clientY >= pr.top && event.clientY <= pr.bottom) {
                return false;
            }
        }
        return true;
    },

    _createInitialPlatforms: function () {
        var list = this.config.modelConfig.objList;
        var pick = function () { return list[Math.floor(Math.random() * list.length)]; };
        this.createPlatform({
            position: { x: 0, y: 0, z: 0 },
            modelId: pick()
        });
        this.createPlatform({
            position: {
                x: this.initialTargetOffset.x,
                y: 0,
                z: this.initialTargetOffset.z
            },
            modelId: pick()
        });
    },

    _createPlacementPreview: function () {
        var mesh;
        if (this.placement.type === 'jumper') {
            var jumperGeometry = new THREE.CylinderGeometry(this.config.jumpTopRadius, this.config.jumpBottomRadius, 1.7, 100);
            jumperGeometry.translate(0, this.config.jumpHeight / 2, 0);
            mesh = new THREE.Mesh(jumperGeometry, new THREE.MeshLambertMaterial({
                color: this.config.jumpColor,
                transparent: true,
                opacity: 0.55
            }));
        } else {
            mesh = new THREE.Group();
            mesh.userData.modelId = this.placement.modelId || this.selectedPlatformModel;
            this._loadPlatformModel({ x: 0, y: 0, z: 0 }, mesh.userData.modelId, function (obj) {
                if (this.placement.preview !== mesh) {
                    this._disposeObject(obj);
                    return;
                }
                obj.traverse(function (child) {
                    if (child.type === 'Mesh') {
                        var materials = child.material instanceof Array ? child.material : [child.material];
                        materials.forEach(function (material) {
                            if (material) {
                                material.transparent = true;
                                material.opacity = 0.62;
                            }
                        });
                    }
                });
                mesh.add(obj);
                this._render();
            }.bind(this));
        }
        mesh.visible = false;
        this.placement.preview = mesh;
        this.group.add(mesh);
    },

    _clearPlacementPreview: function () {
        if (this.placement.preview) {
            this.group.remove(this.placement.preview);
            this._disposeObject(this.placement.preview);
        }
        this.placement.preview = null;
    },

    _getPointerNdc: function (event) {
        var rect = this.canvas.getBoundingClientRect();
        this.pointerVector.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        this.pointerVector.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        return this.pointerVector;
    },

    _getGroundPointFromPointer: function (event) {
        var pointer = this._getPointerNdc(event);
        var plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), this.config.cubeY / 2);
        var worldPoint = new THREE.Vector3();
        this.raycaster.setFromCamera(pointer, this.camera);
        if (!this.raycaster.ray.intersectPlane(plane, worldPoint)) {
            return null;
        }
        return this.group.worldToLocal(worldPoint.clone());
    },

    _getPlatformHitFromPointer: function (event) {
        if (!this.cubes.length) {
            return null;
        }
        var pointer = this._getPointerNdc(event);
        this.raycaster.setFromCamera(pointer, this.camera);
        var hits = this.raycaster.intersectObjects(this.cubes, false);
        if (!hits.length) {
            return null;
        }
        return {
            platform: hits[0].object,
            position: this.group.worldToLocal(hits[0].point.clone())
        };
    },

    _updatePlacementPreview: function (event) {
        if (!this.placement.preview) {
            this._createPlacementPreview();
        }

        if (!this._isPointerOverCanvas(event)) {
            this.placement.preview.visible = false;
            this.placement.lastPosition = null;
            this._render();
            return false;
        }

        if (this.placement.type === 'jumper') {
            var hit = this._getPlatformHitFromPointer(event);
            this.placement.targetPlatform = hit ? hit.platform : null;
            if (!hit) {
                this.placement.preview.visible = false;
                this.placement.lastPosition = null;
                this._render();
                return false;
            }
            this.placement.preview.position.set(hit.position.x, this.config.jumpHeight / 2, hit.position.z);
            this.placement.preview.visible = true;
            this.placement.lastPosition = {
                x: hit.position.x,
                y: this.config.jumpHeight / 2,
                z: hit.position.z
            };
            this._render();
            return true;
        }

        var position = this._getGroundPointFromPointer(event);
        if (!position) {
            this.placement.preview.visible = false;
            this.placement.lastPosition = null;
            this._render();
            return false;
        }
        this.placement.preview.position.set(position.x, 0, position.z);
        this.placement.preview.visible = true;
        this.placement.lastPosition = { x: position.x, y: 0, z: position.z };
        this._render();
        return true;
    },

    _commitPlacementDrag: function () {
        if (!this.placement.lastPosition) {
            this.cancelPlacement();
            return null;
        }

        var created = null;
        if (this.placement.type === 'jumper') {
            this.placeJumperAt(this.placement.targetPlatform, this.placement.lastPosition);
        } else {
            created = this.createPlatform({
                position: this.placement.lastPosition,
                modelId: this.placement.modelId || this.selectedPlatformModel
            });
        }
        this.cancelPlacement();
        this.placementCompletedCallback();
        return created;
    },

    placeJumperAt: function (platform, position) {
        if (!platform || !position) {
            return;
        }
        var jumper = this.createJumper({
            position: {
                x: position.x,
                y: this.config.jumpHeight / 2,
                z: position.z
            }
        });
        this.failAnimationToken += 1;
        this.jumper = jumper;
        window.jumper = this.jumper;
        this.currentCube = platform;
        this.targetCube = this.getNextQueuedPlatform();
        this.mouseState = 0;
        this.resetJumper();
        this.jumper.position.x = position.x;
        this.jumper.position.z = position.z;
        this._render();
    },

    getNextQueuedPlatform: function () {
        var currentIndex = this.cubes.indexOf(this.currentCube);
        if (currentIndex === -1) {
            return null;
        }
        return this.cubes[currentIndex + 1] || null;
    },

    // 随机产生一个图形
    createCube: function () {
        //生成形状
        var cubeType = Math.random() > 0.5 ? 'cube' : 'cylinder';

        var geometry = cubeType === 'cube' ?
            new THREE.CubeGeometry(this.config.cubeX, this.config.cubeY, this.config.cubeZ) :
            new THREE.CylinderGeometry(this.config.cylinderRadius, this.config.cylinderRadius, this.config.cylinderHeight, 100);
        var color = cubeType === 'cube' ? this.config.cubeColor : this.config.cylinderColor;
        var material = new THREE.MeshLambertMaterial({ 
            color: 0x000,
            // color: color,
            transparent: true,
            opacity: 0
        });
        var mesh = new THREE.Mesh(geometry, material);

        // 生成位置
        var relativePos = Math.random() > 0.5 ? 'zDir' : 'xDir';
        if (this.cubes.length) {
            var dis = this.getRandomValue(this.config.cubeMinDis, this.config.cubeMaxDis);
            var lastcube = this.cubes[this.cubes.length - 1];
            if (relativePos === 'zDir') {
                if (cubeType === 'cube') {
                    if (lastcube.geometry instanceof THREE.CubeGeometry){
                        // 方体 -> 方体
                        let pos = {x: lastcube.position.x, y: lastcube.position.y, z: lastcube.position.z - dis - this.config.cubeZ};
                        this.createModel(pos)
                        mesh.position.set(pos.x, pos.y, pos.z);
                    }
                    else {
                        // 方体 -> 圆柱体
                        let pos = {x: lastcube.position.x, y: lastcube.position.y, z: lastcube.position.z - dis - this.config.cylinderRadius - this.config.cubeZ / 2};
                        this.createModel(pos)
                        mesh.position.set(pos.x, pos.y, pos.z);
                    }
                } else {
                    if (lastcube.geometry instanceof THREE.CubeGeometry){
                        //  圆柱体 -> 方体
                        let pos = {x: lastcube.position.x, y: lastcube.position.y, z: lastcube.position.z - dis - this.config.cylinderRadius - this.config.cubeZ / 2};
                        this.createModel(pos)
                        mesh.position.set(pos.x, pos.y, pos.z);
                    }
                    else{
                        // 圆柱体 -> 圆柱体
                        let pos = {x: lastcube.position.x, y: lastcube.position.y, z: lastcube.position.z - dis - this.config.cylinderRadius * 2};
                        this.createModel(pos)
                        mesh.position.set(pos.x, pos.y, pos.z);
                    }
                }
            } else if (relativePos === 'xDir') {
                if (cubeType === 'cube') {
                    if (lastcube.geometry instanceof THREE.CubeGeometry){
                        // 方体 -> 方体
                        let pos = {x: lastcube.position.x + dis + this.config.cubeX, y: lastcube.position.y, z: lastcube.position.z};
                        this.createModel(pos)
                        mesh.position.set(pos.x, pos.y, pos.z);
                    }else{
                        // 方体 -> 圆柱体
                        let pos = {x: lastcube.position.x + dis + this.config.cubeX / 2 + this.config.cylinderRadius, y: lastcube.position.y, z: lastcube.position.z};
                        this.createModel(pos)
                        mesh.position.set(pos.x, pos.y, pos.z);
                    }
                } else {
                    if (lastcube.geometry instanceof THREE.CubeGeometry){
                        // 圆柱体 -> 方体
                        let pos = {x: lastcube.position.x + dis + this.config.cylinderRadius + this.config.cubeX / 2, y: lastcube.position.y, z: lastcube.position.z};
                        this.createModel(pos)
                        mesh.position.set(pos.x, pos.y, pos.z);
                    }
                    else{
                        // 圆柱体 -> 圆柱体
                        let pos = {x: lastcube.position.x + dis + this.config.cylinderRadius * 2, y: lastcube.position.y, z: lastcube.position.z};
                        this.createModel(pos)
                        mesh.position.set(pos.x, pos.y, pos.z);
                    }

                }
            }
        } else {
            this.createModel({x: 0, y: 0, z: 0})
            mesh.position.set(0, 0, 0);
        }

        //渲染
        this.testPosition(mesh.position);
        this.cubes.push(mesh);
        this.group.add(mesh);
        this._render();
        // 如果缓存图形数大于最大缓存数，去掉一个
        if (this.cubes.length > this.config.cubeMaxLen) {
            this.group.remove(this.cubes.shift());
        }
        let _this = this;
        if (_this.cubes.length > 1) {
            // 更新相机位置
            _this._updateCameraPos();
        } else {
            _this.camera.lookAt(this.cameraPos.current);
        }
    },

    // 创建一个弹跳体
    createJumper: function (options) {
        options = options || {};
        var position = options.position || { x: 0, y: this.config.jumpHeight / 2, z: 0 };
        var geometry = new THREE.CylinderGeometry(this.config.jumpTopRadius, this.config.jumpBottomRadius, 1.7, 100);
        var material = new THREE.MeshLambertMaterial({ color: options.color || this.config.jumpColor });
        var mesh = new THREE.Mesh(geometry, material);
        geometry.translate(0, this.config.jumpHeight / 2, 0);
        mesh.position.set(position.x, position.y, position.z);
        mesh.castShadow=true;
        mesh.receiveShadow=true;
        this.jumpers.push(mesh);
        if (options.setActive !== false) {
            this.jumper = mesh;
            window.jumper = this.jumper;
        }
        this.group.add(mesh);
        this._render();
        return mesh;
    },

    createModel: function(position, modelId, platformMesh) {
        var _this = this;
        let name = modelId || this.selectedPlatformModel || this.getRandomItem(this.config.modelConfig.objList).ele;
        this._loadPlatformModel(position, name, function (obj) {
            _this.group.add(obj);
            if (platformMesh) {
                platformMesh.userData.model = obj;
            }
            _this.models.push(obj);
            _this._render();
        });
    },

    _loadPlatformModel: function(position, modelId, callback) {
        let name = modelId || this.selectedPlatformModel || this.getRandomItem(this.config.modelConfig.objList).ele;
        let objConfig = Object.create(this.config.modelConfig[name]);
        objConfig.position = position;

        let prepareModel = (obj) => {
            obj.children.forEach(element => {
                element.traverse(function(o) {
                    if (o.type === 'Mesh') {
                        o.castShadow=true;
                        o.receiveShadow=true;
                    }
                })
            });

            obj.scale.x = objConfig.scale.x;
            obj.scale.y = objConfig.scale.y;
            obj.scale.z = objConfig.scale.z;
            obj.userData.baseScale = {
                x: obj.scale.x,
                y: obj.scale.y,
                z: obj.scale.z
            };
            obj.rotation.x = objConfig.rotation.x * Math.PI;
            obj.rotation.y = objConfig.rotation.y * Math.PI;
            obj.rotation.z = objConfig.rotation.z * Math.PI;
            obj.position.x = objConfig.position.x;
            obj.position.y = objConfig.position.y;
            obj.position.z = objConfig.position.z;
            callback(obj);
        }

        let mtlLoader = new MTLLoader();
        mtlLoader.load(`./res/obj/${name}.mtl`, function (materials) {
            materials.preload();
            let objLoader = new OBJLoader();
            objLoader.setMaterials(materials);
            objLoader.load(`./res/obj/${name}.obj`, prepareModel)
        })
    },

    _disposeObject: function (obj) {
        obj.traverse(function (child) {
            if (child.type === 'Mesh' || child.type === 'Line') {
                if (child.geometry) {
                    child.geometry.dispose();
                }
                if (child.material instanceof Array) {
                    child.material.forEach(function (material) {
                        material.dispose();
                    });
                } else if (child.material) {
                    child.material.dispose();
                }
            }
        });
    },

    removeModel: function(model){
        // 删除内存
        model.children.forEach(element => {
            element.traverse(function(obj) {
                if (obj.type === 'Mesh') {
                  obj.geometry.dispose();
                  if (obj.material instanceof Array){
                        obj.material.forEach(element => {
                            element.dispose();
                        });
                    }else{
                      obj.material.dispose();
                  }
                }
            })
        });
        // 从场景中删除
        this.group.remove(model);
    },

    createPlane: function(){
        var planeGeo = new THREE.PlaneGeometry(10000,10000,10,10);//创建平面
        var planeMat = new THREE.MeshLambertMaterial({  //创建材料
            color:0xFFFF33,
            wireframe:false
        });
        var planeMesh = new THREE.Mesh(planeGeo, planeMat);//创建网格模型
        planeMesh.position.set(0, -this.config.cubeY/2, 0);//设置平面的坐标
        planeMesh.rotation.x = -0.5 * Math.PI;//将平面绕X轴逆时针旋转90度
        planeMesh.receiveShadow = true;//允许接收阴影
        // planeMesh.castShadow = true;//允许接收阴影
        this.viewGroup.add(planeMesh);//将平面添加到场景中

        this.audioManager.play('start');
    },

    _render: function () {
        this.renderer.render(this.scene, this.camera);
        this._updateFlowBubbles();
    },

    _updateCameraPos: function () {

        let a = this.cubes[this.cubes.length - 2];
        let b = this.cubes[this.cubes.length - 1];
        let dis = {
            x: b.position.x - a.position.x,
            y: 0,
            z: b.position.z - a.position.z
        }
        this.groupPos.current = {
            x: this.group.position.x,
            y: this.group.position.y,
            z: this.group.position.z,
        }
        this.groupPos.next = {
            x: this.group.position.x - dis.x,
            y: 0,
            z: this.group.position.z - dis.z,
        }
        // this.cameraPos.current = {
        //     x: this.camera.position.x,
        //     y: this.camera.position.y,
        //     z: this.camera.position.z,
        // }
        // this.cameraPos.next = {
        //     x: this.camera.position.x + dis.x,
        //     y: 0,
        //     z: this.camera.position.z + dis.z,
        // }
        this._updateCamera(0);
    },

    _updateCamera: function (frame) {
        if(frame > this.CAMERA_MOVE_TIME){
            return
        }else frame+=1;

        this.group.position.x = Tween.Quart.easeInOut(frame, this.groupPos.current.x, this.groupPos.next.x-this.groupPos.current.x, this.CAMERA_MOVE_TIME);
        this.group.position.z = Tween.Quart.easeInOut(frame, this.groupPos.current.z, this.groupPos.next.z-this.groupPos.current.z, this.CAMERA_MOVE_TIME);
        
        // this.camera.position.x = this.camera.position.x + this.cameraSpeed.x;
        // this.camera.position.z = this.camera.position.z + this.cameraSpeed.z;
        
        this._render();

        let _this = this;
        requestAnimationFrame(function () {
            _this._updateCamera(frame);
        });
    },

    _registerEvent: function () {
        if (this._eventHandlers) {
            return;
        }
        this._eventHandlers = {
            down: this._onPointerDown.bind(this),
            move: this._onPointerMove.bind(this),
            up: this._onPointerUp.bind(this),
            cancel: this._onPointerCancel.bind(this),
            resize: this._onwindowResize.bind(this)
        };
        this.canvas.style.touchAction = 'none';
        this.canvas.addEventListener('pointerdown', this._eventHandlers.down, { passive: false });
        this.canvas.addEventListener('pointermove', this._eventHandlers.move, { passive: false });
        this.canvas.addEventListener('pointerup', this._eventHandlers.up, { passive: false });
        this.canvas.addEventListener('pointercancel', this._eventHandlers.cancel, { passive: false });
        window.addEventListener('resize', this._eventHandlers.resize, false);
    },

    _destoryEvent: function () {
        if (!this._eventHandlers) {
            return;
        }
        this.canvas.removeEventListener('pointerdown', this._eventHandlers.down);
        this.canvas.removeEventListener('pointermove', this._eventHandlers.move);
        this.canvas.removeEventListener('pointerup', this._eventHandlers.up);
        this.canvas.removeEventListener('pointercancel', this._eventHandlers.cancel);
        window.removeEventListener('resize', this._eventHandlers.resize, false);
        this._eventHandlers = null;
    },

    _onwindowResize: function () {
        this.camera.left = window.innerWidth / -80;
        this.camera.right = window.innerWidth / 80;
        this.camera.top = window.innerHeight / 80;
        this.camera.bottom = window.innerHeight / -80;
        this.camera.updateProjectionMatrix();

        this.renderer.setSize(window.innerWidth, window.innerHeight);
    },

    _onPointerDown: function (event) {
        if (event.pointerType === 'mouse' && event.button !== 0) {
            return;
        }
        this.audioManager.unlock(true);
        event.preventDefault();
        if (this.placement.type) {
            // Placement is active (e.g. user clicked button then clicked canvas separately)
            this._startWindowPlacementDrag(event);
            return;
        }
        this.activePointers[event.pointerId] = {
            x: event.clientX,
            y: event.clientY,
            type: event.pointerType
        };
        if (this.canvas.setPointerCapture) {
            this.canvas.setPointerCapture(event.pointerId);
        }

        var pointers = this._getActivePointerList();
        if (pointers.length >= 2) {
            this._cancelPendingCharge(true);
            this._startPinchGesture(pointers);
            return;
        }

        this.gesture.primaryId = event.pointerId;
        this.gesture.startX = event.clientX;
        this.gesture.startY = event.clientY;
        this.gesture.lastX = event.clientX;
        this.gesture.lastY = event.clientY;

        if (event.pointerType === 'touch') {
            this.gesture.mode = 'pendingJump';
            this.gesture.chargeTimer = setTimeout(function () {
                if (this.gesture.mode === 'pendingJump' && this._getActivePointerList().length === 1) {
                    this._beginJumpCharge();
                }
            }.bind(this), this.viewControl.touchChargeDelay);
        } else {
            this._beginJumpCharge();
        }
    },

    _onPointerMove: function (event) {
        if (!this.activePointers[event.pointerId]) {
            return;
        }
        event.preventDefault();
        this.activePointers[event.pointerId].x = event.clientX;
        this.activePointers[event.pointerId].y = event.clientY;
        var pointers = this._getActivePointerList();

        if (pointers.length >= 2) {
            if (this.gesture.mode !== 'pinching') {
                this._cancelPendingCharge(true);
                this._startPinchGesture(pointers);
            }
            this._updatePinchGesture(pointers);
            return;
        }

        var dx = event.clientX - this.gesture.startX;
        var dy = event.clientY - this.gesture.startY;
        var moved = Math.sqrt(dx * dx + dy * dy);
        if (this.gesture.mode === 'pendingJump' && moved > this.viewControl.dragThreshold) {
            this._cancelPendingCharge(false);
            this.gesture.mode = 'panning';
            this.gesture.lastX = event.clientX;
            this.gesture.lastY = event.clientY;
        }
        if (this.gesture.mode === 'panning') {
            this._panView(event.clientX - this.gesture.lastX, event.clientY - this.gesture.lastY);
            this.gesture.lastX = event.clientX;
            this.gesture.lastY = event.clientY;
        }
    },

    _onPointerUp: function (event) {
        if (event.preventDefault) {
            event.preventDefault();
        }
        var wasCharging = this.gesture.mode === 'charging';
        var wasPending = this.gesture.mode === 'pendingJump';
        delete this.activePointers[event.pointerId];
        if (this.canvas.releasePointerCapture) {
            try {
                this.canvas.releasePointerCapture(event.pointerId);
            } catch (e) {}
        }
        if (wasPending) {
            this._cancelPendingCharge(false);
        }
        if (wasCharging) {
            this._onMouseUp();
            this.gesture.mode = 'idle';
        }

        var pointers = this._getActivePointerList();
        if (pointers.length === 1 && this.gesture.mode === 'pinching') {
            this.gesture.mode = 'panning';
            this.gesture.primaryId = pointers[0].id;
            this.gesture.lastX = pointers[0].x;
            this.gesture.lastY = pointers[0].y;
        } else if (!pointers.length && this.gesture.mode !== 'charging') {
            this.gesture.mode = 'idle';
            this.gesture.primaryId = null;
            this.gesture.pinchLastCenter = null;
        }
    },

    _onPointerCancel: function (event) {
        delete this.activePointers[event.pointerId];
        this._cancelPendingCharge(true);
        this.gesture.mode = 'idle';
        this.gesture.primaryId = null;
        this.gesture.pinchLastCenter = null;
    },

    _getActivePointerList: function () {
        return Object.keys(this.activePointers).map(function (id) {
            var pointer = this.activePointers[id];
            return {
                id: Number(id),
                x: pointer.x,
                y: pointer.y,
                type: pointer.type
            };
        }.bind(this));
    },

    _cancelPendingCharge: function (resetJumper) {
        if (this.gesture.chargeTimer) {
            clearTimeout(this.gesture.chargeTimer);
            this.gesture.chargeTimer = null;
        }
        if (this.mouseState === -1) {
            this.mouseState = 0;
            this.audioManager.stop('push');
            if (resetJumper && this.jumper) {
                this.resetJumper();
                this._render();
            }
        }
    },

    _startPinchGesture: function (pointers) {
        var center = this._getGestureCenter(pointers);
        this.gesture.mode = 'pinching';
        this.gesture.pinchStartDistance = this._getPointerDistance(pointers[0], pointers[1]) || 1;
        this.gesture.pinchStartZoom = this.viewControl.zoom;
        this.gesture.pinchLastCenter = center;
    },

    _updatePinchGesture: function (pointers) {
        var distance = this._getPointerDistance(pointers[0], pointers[1]) || 1;
        var center = this._getGestureCenter(pointers);
        this._setViewZoom(this.gesture.pinchStartZoom * distance / this.gesture.pinchStartDistance, true);
        if (this.gesture.pinchLastCenter) {
            this._panView(center.x - this.gesture.pinchLastCenter.x, center.y - this.gesture.pinchLastCenter.y, true);
        }
        this.gesture.pinchLastCenter = center;
        this._render();
    },

    _getPointerDistance: function (a, b) {
        var dx = a.x - b.x;
        var dy = a.y - b.y;
        return Math.sqrt(dx * dx + dy * dy);
    },

    _getGestureCenter: function (pointers) {
        return {
            x: (pointers[0].x + pointers[1].x) / 2,
            y: (pointers[0].y + pointers[1].y) / 2
        };
    },

    _setViewZoom: function (zoom, skipRender) {
        this.viewControl.zoom = Math.max(this.viewControl.minZoom, Math.min(this.viewControl.maxZoom, zoom));
        this.camera.zoom = this.viewControl.zoom;
        this.camera.updateProjectionMatrix();
        if (!skipRender) {
            this._render();
        }
    },

    _panView: function (deltaX, deltaY, skipRender) {
        var worldPerPixel = (this.camera.top - this.camera.bottom) / window.innerHeight / this.camera.zoom;
        var right = this.panRightVector.setFromMatrixColumn(this.camera.matrix, 0);
        var up = this.panUpVector.setFromMatrixColumn(this.camera.matrix, 1);
        right.y = 0;
        up.y = 0;
        right.normalize();
        up.normalize();
        this.viewGroup.position.add(right.multiplyScalar(deltaX * worldPerPixel));
        this.viewGroup.position.add(up.multiplyScalar(-deltaY * worldPerPixel));
        if (!skipRender) {
            this._render();
        }
    },

    _beginJumpCharge: function () {
        this._cancelPendingCharge(false);
        this.gesture.mode = 'charging';
        this._onMouseDown();
    },

    _onMouseDown: function () {
        if (!this.jumper || !this.currentCube || !this.targetCube) {
            this.gesture.mode = 'idle';
            return;
        }
        // console.log(this.speed, this.accelerate)
        this.mouseState = -1;
        if (this.jumpPressFrame === 0) {
            this.audioManager.play('push');
        }
        this.jumpPressFrame += 1;
        this.jumpChargeDistance = this._getChargedJumpDistance();
        this.jumpChargePower = Math.min(1, this.jumpChargeDistance / Math.max(this._getTargetCenterDistance(), 1));
        var jumpVector = this._getJumpVector();
        var horizontalSpeed = this.jumpChargeDistance / this._getJumpMoveFrameCount();
        this.jumpVelocity.x = jumpVector.x * horizontalSpeed;
        this.jumpVelocity.z = jumpVector.z * horizontalSpeed;
        this._updateJumperChargeShape();
        this._render();
        requestAnimationFrame(function () {
            if (this.mouseState === -1) this._onMouseDown();
        }.bind(this));
    },

    _onMouseUp: function () {
        if (!this.jumper) {
            return;
        }
        if (!this.currentCube || !this.targetCube) {
            this.resetJumper();
            return;
        }
        var self = this;
        this.mouseState = 1;
        this.audioManager.stop('push');
        if (this.currentFrame === -1) {
            this.audioManager.play('push_loop');
        }
        if (this.jumper.position.y >= this.config.jumpHeight / 2) {
            // jumper还在空中运动
            this.currentFrame = this.currentFrame + 1;
            var dir = this.getDirection();
            this.jumper.position.x += this.jumpVelocity.x;
            this.jumper.position.y += this.speed.y;
            this.jumper.position.z += this.jumpVelocity.z;
            if (dir === 'x') {
                this.jumper.rotation.z = this.getRotation();
                // console.log('rZ', this.jumper.rotation.z)
                // console.log('cF', this.currentFrame)
            } else {
                this.jumper.rotation.x = this.getRotation();
                // console.log('rX', this.jumper.rotation.x)
                // console.log('cF', this.currentFrame)
            }
            this._render();
            // 垂直方向先上升后下降
            this.speed.y -= this.accelerate.y;
            // jumper要恢复
            if (this.jumper.scale.y < 1) {
                this.jumper.scale.y = Math.min(1, this.jumper.scale.y + 0.04);
            }
            requestAnimationFrame(function () {
                this._onMouseUp();
            }.bind(this));
        } else {
            // jumper降落了
            var type = this.getJumpState();
            this.resetJumper();
            if (type === 1) {
                // 没有跳到目标平台，回到上一次起跳点继续尝试
                this.returnToLastJumpPoint();
            } else if (type === 2) {
                // 成功降落
                this._animateLandingImpact(this.targetCube);
                this._updateScore(1);
                this.currentCube = this.targetCube;
                this.targetCube = this.getNextQueuedPlatform();
                this.audioManager.play('success');
            } else if (type === 3){
                // 完美降落中心
                this._animateLandingImpact(this.targetCube);
                this._updateScore(3);
                this.currentCube = this.targetCube;
                this.targetCube = this.getNextQueuedPlatform();
                this.audioManager.play('success');
                this.audioManager.play(this.getRandomItem(['cool', 'perfect']).ele);
            } else if (type === -2) {
                // 落到大地上动画
                this.audioManager.play('fail');
                var fallToken = ++this.failAnimationToken;
                function continuefalling() {
                    if (fallToken === self.failAnimationToken && self.jumper.position.y >= -self.config.jumpHeight / 2) {
                        self.jumper.position.y -= 0.06;
                        self._render();
                        requestAnimationFrame(continuefalling);
                    }
                };
                continuefalling()
                if (this.failCallback) {
                    setTimeout(function () {
                        self.failCallback(self.score);
                    }, 1000);
                }
            } else {
                // 落到边缘处
                this.audioManager.play('fail');
                this.failingAnimation(type, ++this.failAnimationToken);
                if (this.failCallback) {
                    setTimeout(function () {
                        self.failCallback(self.score);
                    }, 1000);
                }
            }
        }
    },

    _initScore: function () {
        let el = document.querySelector('#score');
        if(el){
            el.innerHTML = '0';
        }else{
            el = document.createElement('div');
            el.id = "score";
            el.innerHTML = '0';
            document.body.appendChild(el);
        }
    },

    _updateScore: function (digit) {
        // 显示toast
        let t = document.querySelector('.MyToast');
        t.innerHTML = `+${digit}`;
        t.classList.remove('disappear');
        setTimeout(() => {
            t.classList.add('disappear');
        }, 250);
        // 提高分数
        this.score+=digit;
        document.getElementById('score').innerHTML = this.score;
    },

    start: function () {
        this.createPlane();
        this._createInitialPlatforms();
        this.createJumper();
        this._registerEvent();
        this._initScore();
        // this.audioManager.play('bg');
        // this._updateScore(0);
    },

    restart: function () {
        this.flowDemoToken += 1;
        this._clearFlowBubbles();
        for (var i = 0, len = this.cubes.length; i < len; i++) {
            this.group.remove(this.cubes[i]);
        }
        for (var i = 0, len = this.models.length; i < len; i++) {
            this.removeModel(this.models[i]);
        }
        this.models.length = 0;
        for (var j = 0, jLen = this.jumpers.length; j < jLen; j++) {
            this.group.remove(this.jumpers[j]);
        }
        this.jumpers.length = 0;
        this.group.position.x=0;
        this.group.position.z=0;

        this.cameraPos = {
            current: new THREE.Vector3(0, 0, 0), // 摄像机当前的坐标
            next: new THREE.Vector3() // 摄像机即将要移到的位置
        };
        this.cubes = [];
        this.jumper = null;
        window.jumper = this.jumper;
        this.currentCube = null;
        this.targetCube = null;
        this.cancelPlacement();
        this.mouseState = 0;
        this.xspeed = 0;
        this.yspeed = 0;
        this.score = 0;

        this._createInitialPlatforms();
        this.createJumper();
        this._initScore();
        this.audioManager.play('start');
        // this._updateScore(0);
    },

    resetJumper: function () {
        this.currentFrame = -1;
        this.jumper.scale.y = 1;
        this.jumper.scale.x = 1;
        this.jumper.scale.z = 1;
        this.jumper.position.y = this.config.jumpHeight / 2;
        this.jumper.rotation.x = 0;
        this.jumper.rotation.z = 0;
        this.speed.x = 0;
        this.speed.y = this.accelerate.y * this.JUMP_FRAME_NUM / 2;
        this.speed.z = 0;
        this.jumpVelocity.x = 0;
        this.jumpVelocity.z = 0;
        this.jumpChargeDistance = 0;
        this.jumpChargePower = 0;
        this.jumpPressFrame = 0;
    },

    returnToLastJumpPoint: function () {
        if (!this.jumper || !this.currentCube) {
            return;
        }
        this.failAnimationToken += 1;
        this.resetJumper();
        this.jumper.position.x = this.currentCube.position.x;
        this.jumper.position.z = this.currentCube.position.z;
        this.mouseState = 0;
        this._render();
    },

    _getJumpMoveFrameCount: function () {
        // The jumper keeps moving horizontally until the parabolic y position drops below the start height.
        return this.JUMP_FRAME_NUM + 2;
    },

    _getTargetCenterDistance: function () {
        if (!this.jumper || !this.targetCube) {
            return 0;
        }
        var dx = this.targetCube.position.x - this.jumper.position.x;
        var dz = this.targetCube.position.z - this.jumper.position.z;
        return Math.sqrt(dx * dx + dz * dz);
    },

    _getTargetLandingRadius: function () {
        if (!this.targetCube) {
            return this.config.cubeX / 2;
        }
        return this._getPlatformRadius(this.targetCube);
    },

    _getPlatformRadius: function (platform) {
        if (!platform) {
            return this.config.cubeX / 2;
        }
        if (platform.geometry instanceof THREE.CubeGeometry) {
            return Math.min(this.config.cubeX, this.config.cubeZ) / 2;
        }
        return this.config.cylinderRadius;
    },

    _getJumpVector: function () {
        if (!this.jumper || !this.targetCube) {
            return { x: 0, z: 0 };
        }
        var dx = this.targetCube.position.x - this.jumper.position.x;
        var dz = this.targetCube.position.z - this.jumper.position.z;
        var distance = Math.sqrt(dx * dx + dz * dz);
        if (!distance) {
            return { x: 0, z: 0 };
        }
        return {
            x: dx / distance,
            z: dz / distance
        };
    },

    _getChargedJumpDistance: function () {
        var targetCenter = this._getTargetCenterDistance();
        var maxDistance = targetCenter + this._getTargetLandingRadius() + this.config.jumpBottomRadius + 3;
        return Math.min(maxDistance, this.jumpPressFrame * this.CHARGE_DISTANCE_PER_FRAME);
    },

    _updateJumperChargeShape: function () {
        var compression = Math.min(0.34, this.jumpChargePower * 0.28 + this.jumpPressFrame * 0.0008);
        this.jumper.scale.y = 1 - compression;
        this.jumper.scale.x = 1 + compression * 0.28;
        this.jumper.scale.z = 1 + compression * 0.28;
    },

    _getMaxJumpSpeed: function () {
        if (!this.jumper || !this.targetCube) {
            return 0.18;
        }
        var distance = this._getTargetCenterDistance();
        var landingAllowance = this._getTargetLandingRadius() + this.config.jumpBottomRadius;
        return (distance + landingAllowance) / this.JUMP_FRAME_NUM;
    },

    _animateLandingImpact: function (cube) {
        var model = cube && cube.userData && cube.userData.model;
        var baseScale = model && model.userData && model.userData.baseScale;
        var frame = 0;
        var total = 14;
        var self = this;
        function animate() {
            frame += 1;
            var t = frame / total;
            var squash = Math.sin(t * Math.PI);
            self.jumper.scale.y = 1 - squash * 0.12;
            self.jumper.scale.x = 1 + squash * 0.06;
            self.jumper.scale.z = 1 + squash * 0.06;
            if (model && baseScale) {
                model.scale.y = baseScale.y * (1 - squash * 0.045);
                model.scale.x = baseScale.x * (1 + squash * 0.018);
                model.scale.z = baseScale.z * (1 + squash * 0.018);
            }
            self._render();
            if (frame < total) {
                requestAnimationFrame(animate);
            } else {
                self.jumper.scale.x = 1;
                self.jumper.scale.y = 1;
                self.jumper.scale.z = 1;
                if (model && baseScale) {
                    model.scale.x = baseScale.x;
                    model.scale.y = baseScale.y;
                    model.scale.z = baseScale.z;
                }
                self._render();
            }
        }
        animate();
    },

    stop: function () {

    },

    getRandomValue: function (min, max) {
        // min <= value < max
        return Math.floor(Math.random() * (max - min)) + min;
    },

    getRandomItem: function(list){
        let random_i = this.getRandomValue(0, list.length);
        return {
            i: random_i, 
            ele: list[random_i]
        }
    },

    failingAnimation: function (state, token) {
        if (token !== this.failAnimationToken) {
            return;
        }
        var rotateAxis = this.getDirection() === 'z' ? 'x' : 'z';
        var rotateAdd, rotateTo;
        if (state === -1) {
            rotateAdd = this.jumper.rotation[rotateAxis] - 0.1;
            rotateTo = this.jumper.rotation[rotateAxis] > -Math.PI / 2;
        } else {
            rotateAdd = this.jumper.rotation[rotateAxis] + 0.1;
            rotateTo = this.jumper.rotation[rotateAxis] < Math.PI / 2;
        }
        if (rotateTo) {
            this.jumper.rotation[rotateAxis] = rotateAdd;
            this._render();
            requestAnimationFrame(function () {
                this.failingAnimation(state, token);
            }.bind(this));
        } else {
            var self = this;
            function continuefalling() {
                if (token === self.failAnimationToken && self.jumper.position.y >= -self.config.jumpHeight / 2) {
                    self.jumper.position.y -= 0.06;
                    self._render();
                    requestAnimationFrame(continuefalling);
                }
            };
            continuefalling()
        }
    },

    /*
    * 返回值 1： 成功，但落点仍然在当前块上
    * 返回值 2： 成功，落点在下一个块上
    * 返回值 3： 成功，落点在中心点
    * 返回值 -1：失败，落点在当前块边缘 或 在下一个块外边缘
    * 返回值 -2：失败，落点在当前块与下一块之间 或 在下一个块之外
    * 返回值 -3：失败，落点在下一个块内边缘
     */
    getJumpState: function () {
        if (!this.currentCube || !this.targetCube) {
            return 1;
        }
        var jumpR = this.config.jumpBottomRadius;
        var position = this.jumper.position;
        var currentLanding = this._getLandingInfo(this.currentCube, position, jumpR);
        var targetLanding = this._getLandingInfo(this.targetCube, position, jumpR);

        if (currentLanding.inside) {
            return 1;
        }
        if (targetLanding.inside) {
            return targetLanding.centerDistance <= 0.2 ? 3 : 2;
        }
        if (currentLanding.edge || targetLanding.edge) {
            return -1;
        }
        return -2;
    },

    _getLandingInfo: function (platform, position, jumpRadius) {
        var centerDistance = this._getPlanarDistance(position, platform.position);
        if (platform.geometry instanceof THREE.CubeGeometry) {
            var dx = Math.abs(position.x - platform.position.x);
            var dz = Math.abs(position.z - platform.position.z);
            var innerX = this.config.cubeX / 2 - jumpRadius;
            var innerZ = this.config.cubeZ / 2 - jumpRadius;
            var outerX = this.config.cubeX / 2 + jumpRadius;
            var outerZ = this.config.cubeZ / 2 + jumpRadius;
            return {
                centerDistance: centerDistance,
                inside: dx <= innerX && dz <= innerZ,
                edge: dx <= outerX && dz <= outerZ
            };
        }
        var innerRadius = this.config.cylinderRadius - jumpRadius;
        var outerRadius = this.config.cylinderRadius + jumpRadius;
        return {
            centerDistance: centerDistance,
            inside: centerDistance <= innerRadius,
            edge: centerDistance <= outerRadius
        };
    },

    _getPlanarDistance: function (a, b) {
        var dx = a.x - b.x;
        var dz = a.z - b.z;
        return Math.sqrt(dx * dx + dz * dz);
    },

    getCurrentDistance: function () {
        var d, d1, d2, d3, d4;
        var fromObj = this.currentCube || this.cubes[this.cubes.length - 2];
        var fromPosition = fromObj.position;
        var fromType = fromObj.geometry instanceof THREE.CubeGeometry ? 'cube' : 'cylinder';
        var toObj = this.targetCube || this.cubes[this.cubes.length - 1];
        var toPosition = toObj.position;
        var toType = toObj.geometry instanceof THREE.CubeGeometry ? 'cube' : 'cylinder';
        var jumpObj = this.jumper;
        var position = jumpObj.position;

        if (fromType === 'cube') {
            if (toType === 'cube') {
                if (fromPosition.x === toPosition.x) {
                    // -z 方向
                    d = Math.abs(position.z);
                    d1 = Math.abs(fromPosition.z - this.config.cubeZ / 2);
                    d2 = Math.abs(toPosition.z + this.config.cubeZ / 2);
                    d3 = Math.abs(toPosition.z);
                    d4 = Math.abs(toPosition.z - this.config.cubeZ / 2);
                } else {
                    // x 方向
                    d = Math.abs(position.x);
                    d1 = Math.abs(fromPosition.x + this.config.cubeX / 2);
                    d2 = Math.abs(toPosition.x - this.config.cubeX / 2);
                    d3 = Math.abs(toPosition.x);
                    d4 = Math.abs(toPosition.x + this.config.cubeX / 2);
                }
            } else {
                if (fromPosition.x === toPosition.x) {
                    // -z 方向
                    d = Math.abs(position.z);
                    d1 = Math.abs(fromPosition.z - this.config.cubeZ / 2);
                    d2 = Math.abs(toPosition.z + this.config.cylinderRadius);
                    d3 = Math.abs(toPosition.z);
                    d4 = Math.abs(toPosition.z - this.config.cylinderRadius);
                } else {
                    // x 方向
                    d = Math.abs(position.x);
                    d1 = Math.abs(fromPosition.x + this.config.cubeX / 2);
                    d2 = Math.abs(toPosition.x - this.config.cylinderRadius);
                    d3 = Math.abs(toPosition.x);
                    d4 = Math.abs(toPosition.x + this.config.cylinderRadius);
                }
            }
        } else {
            if (toType === 'cube') {
                if (fromPosition.x === toPosition.x) {
                    // -z 方向
                    d = Math.abs(position.z);
                    d1 = Math.abs(fromPosition.z - this.config.cylinderRadius);
                    d2 = Math.abs(toPosition.z + this.config.cubeZ / 2);
                    d3 = Math.abs(toPosition.z);
                    d4 = Math.abs(toPosition.z - this.config.cubeZ / 2);
                } else {
                    // x 方向
                    d = Math.abs(position.x);
                    d1 = Math.abs(fromPosition.x + this.config.cylinderRadius);
                    d2 = Math.abs(toPosition.x - this.config.cubeX / 2);
                    d3 = Math.abs(toPosition.x);
                    d4 = Math.abs(toPosition.x + this.config.cubeX / 2);
                }
            } else {
                if (fromPosition.x === toPosition.x) {
                    // -z 方向
                    d = Math.abs(position.z);
                    d1 = Math.abs(fromPosition.z - this.config.cylinderRadius);
                    d2 = Math.abs(toPosition.z + this.config.cylinderRadius);
                    d3 = Math.abs(toPosition.z);
                    d4 = Math.abs(toPosition.z - this.config.cylinderRadius);
                } else {
                    // x 方向
                    d = Math.abs(position.x);
                    d1 = Math.abs(fromPosition.x + this.config.cylinderRadius);
                    d2 = Math.abs(toPosition.x - this.config.cylinderRadius);
                    d3 = Math.abs(toPosition.x);
                    d4 = Math.abs(toPosition.x + this.config.cylinderRadius);
                }
            }
        }

        return { d: d, d1: d1, d2: d2, d3: d3, d4: d4 };
    },

    getNextDistance: function () {
        if (!this.currentCube || !this.targetCube) {
            return { x: 0, y: 0, z: 0 };
        }
        var toObj = this.targetCube;
        var toPosition = toObj.position;
        var jumpObj = this.jumper;
        var position = jumpObj.position;

        var direction = this.getDirection();
        var distance = {
            x: 0,   //暂时没用，先初始化0
            y: 0,   //暂时没用，先初始化0
            z: 0
        }
        if (direction === 'x') {
            distance.z = toPosition.z - position.z
        } else if (direction === 'z') {
            distance.z = toPosition.x - position.x
        }
        return distance;
    },

    getDirection: function () {
        var direction = 'x';
        if (this.currentCube && this.targetCube) {
            var from = this.currentCube;
            var to = this.targetCube;
            if (Math.abs(from.position.z - to.position.z) > Math.abs(from.position.x - to.position.x)) {
                direction = 'z';
            }
        }
        return direction;
    },

    getRotation: function () {
        let time = this.currentFrame;
        return -Tween.Sine.easeInOut(time, 0, 2 * Math.PI, this.JUMP_FRAME_NUM);
    },

    testPosition: function (position) {
        if (isNaN(position.x) || isNaN(position.y) || isNaN(position.z)) {
            console.log('position incorrect！');
        }
    },

    isPC: function () {
        var userAgentInfo = navigator.userAgent;
        var Agents = ["Android", "iPhone",
        "SymbianOS", "Windows Phone",
        "iPad", "iPod"];
        var flag = true;
        for (var v = 0; v < Agents.length; v++) {
            if (userAgentInfo.indexOf(Agents[v]) > 0) {
                flag = false;
                break;
            }
        }
        // console.log(userAgentInfo, flag)
        return flag;
    },
});

module.exports = Game