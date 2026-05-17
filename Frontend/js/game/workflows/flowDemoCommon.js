'use strict'

var FlowRuntimeUtils = require('./flowRuntimeUtils')

function sayStage(node, stage, context, delay) {
    var action = {
        type: 'sayStage',
        node: node,
        stage: stage
    };
    if (context) {
        action.context = context;
    }
    if (delay) {
        action.delay = delay;
    }
    return action;
}

function pulse(node, subtle) {
    return {
        type: 'pulse',
        node: node,
        subtle: !!subtle
    };
}

function jump(from, to, holdBefore) {
    var action = {
        type: 'jump',
        from: from,
        to: to
    };
    if (holdBefore) {
        action.holdBefore = holdBefore;
    }
    return action;
}

// Charge batch jump: hold on from node, release to arc to each worker platform
function chargedBatchJump(from, workers) {
    return {
        type: 'chargedBatchJump',
        from: from,
        workers: workers.slice()
    };
}

// Charge merge jump: all jumpers land on the same target platform
function chargedMergeJump(jumpers, to) {
    return {
        type: 'chargedMergeJump',
        jumpers: jumpers.slice(),
        to: to
    };
}

function buildResultSnippet(template, nodeId, userTask) {
    var node = FlowRuntimeUtils.getTemplateNode(template, nodeId);
    var taskText = (userTask || '').trim();
    var label = node ? (node.label || node.role || 'Agent') : 'Agent';
    if (!taskText) {
        return label + ' summarized the key conclusions';
    }
    return 'On "' + taskText + '", ' + label + ' summarized the key conclusions';
}

function resultContext(template, nodeId, userTask, extra) {
    var context = extra || {};
    context.result = buildResultSnippet(template, nodeId, userTask);
    return context;
}

function buildLinearJumpActions(template, taskText) {
    var sequence = template.jumpSequence || [];
    var actions = [];
    for (var i = 0; i < sequence.length; i++) {
        var nodeId = sequence[i];
        var nextId = sequence[i + 1];
        actions.push(sayStage(
            nodeId,
            i === 0 ? 'start' : 'receive',
            i === 0 ? (nextId ? { target: nextId } : {}) : { source: sequence[i - 1], target: nextId }
        ));
        if (nextId) {
            actions.push(sayStage(nodeId, 'handoff', { target: nextId }, 1180));
            actions.push(jump(nodeId, nextId, 920));
        } else {
            actions.push(sayStage(nodeId, 'result', resultContext(template, nodeId, taskText)));
        }
    }
    return actions;
}

module.exports = {
    sayStage: sayStage,
    pulse: pulse,
    jump: jump,
    chargedBatchJump: chargedBatchJump,
    chargedMergeJump: chargedMergeJump,
    buildResultSnippet: buildResultSnippet,
    resultContext: resultContext,
    buildLinearJumpActions: buildLinearJumpActions
}
