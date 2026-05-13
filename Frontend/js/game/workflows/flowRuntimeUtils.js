'use strict'

function getTemplateNode(template, nodeId) {
    var nodes = template && template.nodes ? template.nodes : [];
    for (var i = 0; i < nodes.length; i++) {
        if (nodes[i].id === nodeId) {
            return nodes[i];
        }
    }
    return null;
}

function getDialogText(template, node, userTask) {
    var taskText = (userTask || '').trim();
    var dialog = template.dialogues && template.dialogues[node.id];
    if (!taskText) {
        return node.label || node.role || 'Agent';
    }
    if (dialog && typeof dialog === 'object' && !Array.isArray(dialog)) {
        var fallback = dialog.default || dialog.start;
        if (typeof fallback === 'function') {
            return fallback(taskText, {});
        }
        if (typeof fallback === 'string') {
            return fallback;
        }
        return node.label || node.role || 'Agent';
    }
    if (typeof dialog === 'function') {
        return dialog(taskText);
    }
    return dialog || ((node.label || node.role || 'Agent') + ' 处理：' + taskText);
}

function getFlowNodeLabel(template, nodeId) {
    var node = getTemplateNode(template, nodeId);
    if (!node) {
        return nodeId || 'Agent';
    }
    return node.label || node.role || nodeId || 'Agent';
}

function resolveDialogEntry(entry, taskText, context) {
    if (typeof entry === 'function') {
        return entry(taskText, context || {});
    }
    return entry || '';
}

function getDialogByStage(template, nodeId, stage, userTask, context) {
    var taskText = (userTask || '').trim();
    var node = getTemplateNode(template, nodeId);
    var dialogues = template.dialogues || {};
    var dialog = dialogues[nodeId];
    if (!node) {
        return '';
    }
    if (dialog && typeof dialog === 'object' && !Array.isArray(dialog)) {
        var stageOrder = [stage, 'default', 'start'];
        for (var i = 0; i < stageOrder.length; i++) {
            var entry = dialog[stageOrder[i]];
            if (!entry) {
                continue;
            }
            var resolved = resolveDialogEntry(entry, taskText, context);
            if (resolved) {
                return resolved;
            }
        }
    }
    return getDialogText(template, node, taskText);
}

function normalizeActionContext(template, context) {
    var nextContext = {};
    var key;
    context = context || {};
    for (key in context) {
        if (Object.prototype.hasOwnProperty.call(context, key)) {
            nextContext[key] = context[key];
        }
    }
    if (nextContext.source) {
        nextContext.sourceLabel = getFlowNodeLabel(template, nextContext.source);
    }
    if (nextContext.target) {
        nextContext.targetLabel = getFlowNodeLabel(template, nextContext.target);
    }
    return nextContext;
}

function getAgentColor(role) {
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
}

function getFlowTemplateBounds(template) {
    var nodes = template && template.nodes ? template.nodes : [];
    var bounds = {
        minX: Infinity,
        maxX: -Infinity,
        minZ: Infinity,
        maxZ: -Infinity
    };
    for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        bounds.minX = Math.min(bounds.minX, node.x);
        bounds.maxX = Math.max(bounds.maxX, node.x);
        bounds.minZ = Math.min(bounds.minZ, node.z);
        bounds.maxZ = Math.max(bounds.maxZ, node.z);
    }
    if (!nodes.length) {
        bounds.minX = bounds.maxX = bounds.minZ = bounds.maxZ = 0;
    }
    bounds.centerX = (bounds.minX + bounds.maxX) / 2;
    bounds.centerZ = (bounds.minZ + bounds.maxZ) / 2;
    return bounds;
}

module.exports = {
    getTemplateNode: getTemplateNode,
    getDialogText: getDialogText,
    getFlowNodeLabel: getFlowNodeLabel,
    resolveDialogEntry: resolveDialogEntry,
    getDialogByStage: getDialogByStage,
    normalizeActionContext: normalizeActionContext,
    getAgentColor: getAgentColor,
    getFlowTemplateBounds: getFlowTemplateBounds
}
