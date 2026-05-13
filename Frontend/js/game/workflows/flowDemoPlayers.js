'use strict'

var sequential = require('./flowDemoSequential')

var playersByVisualMode = {
    linear_jump: sequential,
    router_branch: require('./flowDemoRouter'),
    parallel_fanout: require('./flowDemoParallel'),
    loop_review: require('./flowDemoLoop'),
    debate_round: require('./flowDemoDebate'),
    hierarchical_delegate: require('./flowDemoHierarchical'),
    supervisor_dispatch: require('./flowDemoSupervisor')
}

function getPlayer(template) {
    return playersByVisualMode[template && template.visualMode] || sequential;
}

function buildActions(template, taskText) {
    return getPlayer(template).buildActions(template, taskText);
}

module.exports = {
    buildActions: buildActions
}
