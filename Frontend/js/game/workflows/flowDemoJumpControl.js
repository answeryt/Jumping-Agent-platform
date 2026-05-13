'use strict'

var FlowRuntimeUtils = require('./flowRuntimeUtils')

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
        if (returnJumper && returnJumper !== game.flowJumperMap[activeAction.to]) {
            game.removeJumper(returnJumper);
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

function beginJumpCharge(game, fromUserInput) {
    if (fromUserInput !== true) {
        return false;
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
    showJumpPrompt: showJumpPrompt,
    activateJump: activateJump,
    finishJump: finishJump,
    beginJumpCharge: beginJumpCharge
}
