'use strict'

var common = require('./flowDemoCommon')

function buildActions(template, taskText) {
    var actions = [
        common.sayStage(template.supervisor, 'start'),
        common.pulse(template.supervisor, true)
    ];
    for (var i = 0; i < template.agents.length; i++) {
        var agentId = template.agents[i];
        actions.push(common.sayStage(template.supervisor, 'delegate', { target: agentId }));
        actions.push(common.jump(template.supervisor, agentId, 820));
        actions.push(common.sayStage(agentId, 'start'));
        actions.push(common.pulse(agentId));
        actions.push(common.sayStage(agentId, 'done', { target: template.supervisor }));
        actions.push(common.jump(agentId, template.supervisor, 820));
        actions.push(common.sayStage(
            agentId,
            'result',
            common.resultContext(template, agentId, taskText, { target: template.supervisor })
        ));
        actions.push(common.sayStage(template.supervisor, 'receive', { source: agentId }));
    }
    actions.push(common.sayStage(template.supervisor, 'final'));
    actions.push(common.pulse(template.supervisor, true));
    return actions;
}

module.exports = {
    buildActions: buildActions
}
