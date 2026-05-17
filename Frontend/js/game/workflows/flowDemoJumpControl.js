'use strict'

var FlowRuntimeUtils = require('./flowRuntimeUtils')

// ── Single jump (worker → aggregator) ──────────────────────────────────────

function isChargingEnabled(game) {
    return !!(
        game.flowDemoState &&
        game.flowDemoState.active &&
        game.flowDemoState.awaitingJump &&
        game.flowDemoState.pendingJumpAction &&
        !game.flowDemoState.jumpInProgress
    );
}

function isJumpActive(game) {
    return !!(
        game.flowDemoState &&
        game.flowDemoState.active &&
        game.flowDemoState.jumpInProgress &&
        game.flowDemoState.activeJumpAction &&
        game.flowDemoState.jumper &&
        game.flowDemoState.toPlatform
    );
}

function queueJump(game, template, action, token, done) {
    if (token !== game.flowDemoToken) {
        if (done) done();
        return;
    }
    if (game.flowDemoState.queuedNextTimer) {
        clearTimeout(game.flowDemoState.queuedNextTimer);
        game.flowDemoState.queuedNextTimer = null;
    }
    game.flowDemoState.templateId = template ? template.id : null;
    game.flowDemoState.token = token;
    game.flowDemoState.pendingJumpAction = action;
    game.flowDemoState.pendingJumpDone = done;
    game.flowDemoState.activeJumpAction = null;
    game.flowDemoState.activeJumpDone = null;
    game.flowDemoState.awaitingJump = true;
    game.flowDemoState.jumpInProgress = false;
    game.flowDemoState.jumper = null;
    game.flowDemoState.fromPlatform = null;
    game.flowDemoState.toPlatform = null;
    game.flowDemoState.returnJumper = null;
    game.flowDemoState.previousCurrentCube = null;
    game.flowDemoState.previousTargetCube = null;
    showJumpPrompt(game, template, action);
}

function showJumpPrompt(game, template, action) {
    if (!template || !action || !action.from) {
        return;
    }
    var fromJumper = game.flowJumperMap[action.from];
    if (!fromJumper) {
        return;
    }
    var promptText = FlowRuntimeUtils.getDialogByStage(
        template,
        action.from,
        'promptNext',
        game.flowDemoState.userTask,
        FlowRuntimeUtils.normalizeActionContext(template, { target: action.to })
    );
    if (promptText) {
        game._setFlowBubbleText(fromJumper, promptText);
    }
}

function activateJump(game) {
    if (!isChargingEnabled(game)) {
        return false;
    }
    var action = game.flowDemoState.pendingJumpAction;
    var fromJumper = action ? game.flowJumperMap[action.from] : null;
    var targetPlatform = action ? game.flowNodeMap[action.to] : null;
    if (!action || !fromJumper || !targetPlatform) {
        return false;
    }
    game.flowDemoState.awaitingJump = false;
    game.flowDemoState.jumpInProgress = true;
    game.flowDemoState.activeJumpAction = action;
    game.flowDemoState.activeJumpDone = game.flowDemoState.pendingJumpDone;
    game.flowDemoState.pendingJumpAction = null;
    game.flowDemoState.pendingJumpDone = null;
    game.flowDemoState.jumper = fromJumper;
    game.flowDemoState.toPlatform = targetPlatform;
    game.flowDemoState.fromPlatform = {
        position: {
            x: fromJumper.position.x,
            y: 0,
            z: fromJumper.position.z
        }
    };
    game.flowDemoState.returnJumper = game.jumper;
    game.flowDemoState.previousCurrentCube = game.currentCube;
    game.flowDemoState.previousTargetCube = game.targetCube;
    game.jumper = fromJumper;
    game.currentCube = game.flowDemoState.fromPlatform;
    game.targetCube = targetPlatform;
    return true;
}

function finishJump(game) {
    var done = game.flowDemoState.activeJumpDone;
    var returnJumper = game.flowDemoState.returnJumper;
    var previousCurrentCube = game.flowDemoState.previousCurrentCube;
    var previousTargetCube = game.flowDemoState.previousTargetCube;
    var activeAction = game.flowDemoState.activeJumpAction;
    var fromJumper = activeAction && activeAction.from ? game.flowJumperMap[activeAction.from] : null;
    var sourcePosition = game.flowDemoState.fromPlatform && game.flowDemoState.fromPlatform.position;
    var targetPlatform = activeAction && activeAction.to ? game.flowNodeMap[activeAction.to] : null;
    if (game.flowDemoState.queuedNextTimer) {
        clearTimeout(game.flowDemoState.queuedNextTimer);
    }
    game.flowDemoState.jumpInProgress = false;
    game.flowDemoState.activeJumpAction = null;
    game.flowDemoState.activeJumpDone = null;
    game.flowDemoState.jumper = null;
    game.flowDemoState.fromPlatform = null;
    game.flowDemoState.toPlatform = null;
    game.flowDemoState.returnJumper = null;
    game.flowDemoState.previousCurrentCube = null;
    game.flowDemoState.previousTargetCube = null;
    if (targetPlatform) {
        if (fromJumper && sourcePosition) {
            fromJumper.position.set(sourcePosition.x, game.config.jumpHeight / 2, sourcePosition.z);
        }
        game.jumper = game.flowJumperMap[activeAction.to] || returnJumper || game.jumper;
        window.jumper = game.jumper;
        game.currentCube = targetPlatform;
        game.targetCube = previousTargetCube || null;
    } else {
        game.jumper = returnJumper || game.jumper;
        game.currentCube = previousCurrentCube || game.currentCube;
        game.targetCube = previousTargetCube || game.targetCube;
    }
    if (done) {
        game.flowDemoState.queuedNextTimer = window.setTimeout(function () {
            game.flowDemoState.queuedNextTimer = null;
            done();
        }, 260);
    } else {
        game.flowDemoState.queuedNextTimer = null;
    }
}

// ── Charge batch jump (dispatcher → N workers) ─────────────────────────────

function queueChargedBatchJump(game, template, action, token, done) {
    if (token !== game.flowDemoToken) {
        if (done) done();
        return;
    }
    if (game.flowDemoState.queuedNextTimer) {
        clearTimeout(game.flowDemoState.queuedNextTimer);
        game.flowDemoState.queuedNextTimer = null;
    }
    game.flowDemoState.awaitingChargedBatchJump = true;
    game.flowDemoState.pendingChargedBatchJumpAction = action;
    game.flowDemoState.pendingChargedBatchJumpDone = done;
    game.flowDemoState.chargedBatchJumpCharging = false;
    game.flowDemoState.chargedBatchJumpReturnState = null;

    var fromJumper = game.flowJumperMap[action.from];
    if (fromJumper) {
        var promptText = FlowRuntimeUtils.getDialogByStage(
            template,
            action.from,
            'promptNext',
            game.flowDemoState.userTask,
            FlowRuntimeUtils.normalizeActionContext(template, {})
        );
        if (promptText) {
            game._setFlowBubbleText(fromJumper, promptText);
        }
    }
}

function queueChargedMergeJump(game, template, action, token, done) {
    if (token !== game.flowDemoToken) {
        if (done) done();
        return;
    }
    if (game.flowDemoState.queuedNextTimer) {
        clearTimeout(game.flowDemoState.queuedNextTimer);
        game.flowDemoState.queuedNextTimer = null;
    }
    game.flowDemoState.awaitingChargedBatchJump = true;
    game.flowDemoState.pendingChargedBatchJumpAction = action;
    game.flowDemoState.pendingChargedBatchJumpDone = done;
    game.flowDemoState.chargedBatchJumpCharging = false;
    game.flowDemoState.chargedBatchJumpReturnState = null;

    for (var i = 0; i < action.jumpers.length; i++) {
        var nodeId = action.jumpers[i];
        var jumper = game.flowJumperMap[nodeId];
        if (!jumper) continue;
        var promptText = FlowRuntimeUtils.getDialogByStage(
            template,
            nodeId,
            'promptNext',
            game.flowDemoState.userTask,
            FlowRuntimeUtils.normalizeActionContext(template, { target: action.to })
        );
        if (promptText) {
            game._setFlowBubbleText(jumper, promptText);
        }
    }
}

function activateChargedBatchJump(game) {
    if (!game.flowDemoState.awaitingChargedBatchJump || game.flowDemoState.chargedBatchJumpCharging) {
        return false;
    }
    var action = game.flowDemoState.pendingChargedBatchJumpAction;
    if (!action) return false;

    var activeNodeId = action.from || (action.jumpers && action.jumpers[0]);
    var activeJumper = activeNodeId ? game.flowJumperMap[activeNodeId] : null;
    var activePlatform = activeNodeId ? game.flowNodeMap[activeNodeId] : null;
    var refNodeId = action.to || (action.workers && action.workers[0]);
    var refPlatform = refNodeId ? game.flowNodeMap[refNodeId] : null;

    if (!activeJumper || !activePlatform || !refPlatform) return false;

    game.flowDemoState.chargedBatchJumpReturnState = {
        jumper: game.jumper,
        currentCube: game.currentCube,
        targetCube: game.targetCube
    };

    game.flowDemoState.awaitingChargedBatchJump = false;
    game.flowDemoState.chargedBatchJumpCharging = true;

    game.jumper = activeJumper;
    window.jumper = game.jumper;
    game.currentCube = {
        position: {
            x: activePlatform.position.x,
            y: 0,
            z: activePlatform.position.z
        }
    };
    game.targetCube = refPlatform;
    return true;
}

function beginJumpCharge(game, fromUserInput) {
    if (fromUserInput !== true) {
        return false;
    }
    if (activateChargedBatchJump(game)) {
        game._cancelPendingCharge(false);
        game.gesture.mode = 'charging';
        game._onMouseDown();
        return true;
    }
    if (!activateJump(game)) {
        return false;
    }
    game._cancelPendingCharge(false);
    game.gesture.mode = 'charging';
    game._onMouseDown();
    return true;
}

module.exports = {
    isChargingEnabled: isChargingEnabled,
    isJumpActive: isJumpActive,
    queueJump: queueJump,
    queueChargedBatchJump: queueChargedBatchJump,
    queueChargedMergeJump: queueChargedMergeJump,
    showJumpPrompt: showJumpPrompt,
    activateJump: activateJump,
    activateChargedBatchJump: activateChargedBatchJump,
    finishJump: finishJump,
    beginJumpCharge: beginJumpCharge
}
