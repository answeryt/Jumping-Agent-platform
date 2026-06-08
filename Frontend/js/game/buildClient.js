'use strict'

var ORCHESTRATOR_PORT = '8001'
var DEFAULT_ORCHESTRATOR_URL = 'ws://localhost:' + ORCHESTRATOR_PORT + '/ws/project-build'

function getDefaultWsUrl() {
    if (typeof window === 'undefined' || !window.location || !window.location.hostname) {
        return DEFAULT_ORCHESTRATOR_URL;
    }
    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return protocol + '//' + window.location.hostname + ':' + ORCHESTRATOR_PORT + '/ws/project-build';
}

function getWsUrl() {
    if (typeof window !== 'undefined' && window.AGENT_ORCHESTRATOR_WS_URL) {
        return window.AGENT_ORCHESTRATOR_WS_URL;
    }
    return getDefaultWsUrl();
}

function slugify(value, fallback) {
    var raw = (value || '').toString().trim().toLowerCase().replace(/-/g, '_');
    var normalized = raw.replace(/[^a-z0-9_]+/g, '_').replace(/_+/g, '_').replace(/^_+|_+$/g, '');
    return normalized || fallback;
}

function numericProjectName() {
    return String(Date.now());
}

function dedupeName(candidate, used) {
    if (!used[candidate]) {
        used[candidate] = true;
        return candidate;
    }
    var index = 2;
    while (used[candidate + '_' + index]) {
        index++;
    }
    var next = candidate + '_' + index;
    used[next] = true;
    return next;
}

function resolveModelProfile(role) {
    if (role === 'dispatcher' || role === 'manager' || role === 'moderator') {
        return 'reasoning';
    }
    if (role === 'evaluator') {
        return 'balanced';
    }
    return 'balanced';
}

function resolveDeliverable(role, index, total) {
    if (role === 'evaluator') {
        return 'review';
    }
    if (index === 0 || role === 'dispatcher' || role === 'manager') {
        return 'plan';
    }
    if (index === total - 1) {
        return 'artifact';
    }
    return 'analysis';
}

function buildNodes(template, taskText, platformToolMap, platformTaskMap) {
    var nodes = [{
        id: 'user',
        type: 'user',
        label: taskText ? 'User requirement: ' + taskText : 'User requirement',
        shape: 'user',
        position: { x: -16, y: 0 },
        config: {}
    }];
    var usedNames = {};
    var agentNameByNodeId = {};
    var templateNodes = template.nodes || [];

    for (var i = 0; i < templateNodes.length; i++) {
        var node = templateNodes[i];
        var label = node.label || node.id || ('Agent ' + (i + 1));
        var agentName = dedupeName(slugify(label, 'agent_' + (i + 1)), usedNames);
        var selectedTools = Array.isArray(platformToolMap && platformToolMap[node.id])
            ? platformToolMap[node.id].filter(function (toolId, index, items) {
                return toolId && items.indexOf(toolId) === index;
            })
            : [];
        var platformTask = platformTaskMap && platformTaskMap[node.id];
        agentNameByNodeId[node.id] = agentName;
        nodes.push({
            id: node.id,
            type: 'agent',
            label: label,
            shape: node.role || 'agent',
            position: {
                x: typeof node.x === 'number' ? node.x : 0,
                y: typeof node.z === 'number' ? node.z : 0
            },
            config: {
                name: agentName,
                responsibility: buildResponsibility(label, taskText, node.role, platformTask),
                deliverable: resolveDeliverable(node.role, i, templateNodes.length),
                modelProfile: resolveModelProfile(node.role),
                autonomy: node.role === 'dispatcher' || node.role === 'manager' ? 'adaptive' : 'structured',
                guidance: 'This agent was generated from the jump workflow canvas node "' + label + '".',
                tools: selectedTools,
                capabilities: {}
            }
        });
    }

    return {
        nodes: nodes,
        agentNameByNodeId: agentNameByNodeId
    };
}

function buildResponsibility(label, taskText, role, platformTask) {
    var prefix = role ? '[' + role + '] ' : '';
    var customTask = (platformTask || '').toString().trim();
    if (customTask && customTask !== label) {
        if (taskText) {
            return prefix + 'For user task "' + taskText + '", responsible for: "' + customTask + '".';
        }
        return prefix + 'Responsible for: "' + customTask + '".';
    }
    if (taskText) {
        return prefix + 'Complete the "' + label + '" stage for user task "' + taskText + '".';
    }
    return prefix + 'Complete the "' + label + '" stage.';
}

function addEdge(edges, used, source, target, mode) {
    if (!source || !target || source === target) {
        return;
    }
    var key = source + '->' + target + ':' + mode;
    if (used[key]) {
        return;
    }
    used[key] = true;
    edges.push({
        id: 'edge_' + edges.length,
        source: source,
        target: target,
        mode: mode,
        style: mode
    });
}

function buildEdges(template) {
    var edges = [];
    var used = {};
    var sequence = template.jumpSequence || [];

    if (sequence.length) {
        addEdge(edges, used, 'user', sequence[0], 'static');
        for (var i = 0; i < sequence.length - 1; i++) {
            addEdge(edges, used, sequence[i], sequence[i + 1], 'static');
        }
        return edges;
    }

    var nodes = template.nodes || [];
    if (nodes.length) {
        addEdge(edges, used, 'user', nodes[0].id, 'static');
    }
    for (var j = 0; j < nodes.length - 1; j++) {
        addEdge(edges, used, nodes[j].id, nodes[j + 1].id, 'static');
    }
    return edges;
}

function buildGraphSpec(template, taskText, platformToolMap, platformTaskMap) {
    var builtNodes = buildNodes(template, taskText, platformToolMap || {}, platformTaskMap || {});
    var projectName = numericProjectName();
    return {
        projectId: 'jump_' + slugify(template.id || 'project', 'project'),
        projectName: projectName,
        task: taskText || '',
        nodes: builtNodes.nodes,
        edges: buildEdges(template)
    };
}

function connectAndBuild(template, taskText, handlers, platformToolMap, platformTaskMap) {
    handlers = handlers || {};
    if (!template) {
        throw new Error('Please select a flow template first');
    }
    var graph = buildGraphSpec(template, taskText || '', platformToolMap || {}, platformTaskMap || {});
    var socket = new WebSocket(getWsUrl());
    var buildStarted = false;

    socket.onopen = function () {
        if (handlers.onStatus) {
            handlers.onStatus('Connected to backend, submitting flow graph...');
        }
        socket.send(JSON.stringify({
            type: 'graph.submit',
            payload: graph
        }));
    };

    socket.onmessage = function (event) {
        var message;
        try {
            message = JSON.parse(event.data);
        } catch (error) {
            if (handlers.onError) {
                handlers.onError('Backend returned an unparseable message');
            }
            return;
        }
        if (handlers.onEvent) {
            handlers.onEvent(message);
        }
        if (message.type === 'graph.validated' && !buildStarted) {
            buildStarted = true;
            if (handlers.onStatus) {
                handlers.onStatus('Flow graph validated, building agents...');
            }
            socket.send(JSON.stringify({ type: 'build.start', payload: {} }));
        } else if (message.type === 'graph.invalid' || message.type === 'build.failed' || message.type === 'error') {
            if (handlers.onError) {
                handlers.onError((message.payload && (message.payload.error || message.payload.message)) || 'Build failed');
            }
            socket.close();
        } else if (message.type === 'build.finished') {
            if (handlers.onFinished) {
                handlers.onFinished(message.payload || {});
            }
            socket.close();
        }
    };

    socket.onerror = function () {
        if (handlers.onError) {
            handlers.onError('Cannot connect to Orchestrator (' + getWsUrl() + '). Ensure the backend is listening on port 8001 (0.0.0.0).');
        }
    };

    return {
        socket: socket,
        graph: graph
    };
}

module.exports = {
    buildGraphSpec: buildGraphSpec,
    connectAndBuild: connectAndBuild
}
