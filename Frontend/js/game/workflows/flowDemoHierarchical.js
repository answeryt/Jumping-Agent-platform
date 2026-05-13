'use strict'

var common = require('./flowDemoCommon')

function buildActions(template, taskText) {
    var actions = [
        common.sayStage(template.manager, 'start'),
        common.pulse(template.manager, true)
    ];
    for (var i = 0; i < template.workers.length; i++) {
        var workerId = template.workers[i];
        actions.push(common.sayStage(template.manager, 'delegate', { target: workerId }));
        actions.push(common.jump(template.manager, workerId, 820));
        actions.push(common.sayStage(workerId, 'start'));
        actions.push(common.pulse(workerId));
        actions.push(common.sayStage(workerId, 'done', { target: template.manager }));
        actions.push(common.jump(workerId, template.manager, 820));
        actions.push(common.sayStage(
            workerId,
            'result',
            common.resultContext(template, workerId, taskText, { target: template.manager })
        ));
        actions.push(common.sayStage(template.manager, 'receive', { source: workerId }));
    }
    actions.push(common.sayStage(template.manager, 'delegate', { target: template.final }));
    actions.push(common.jump(template.manager, template.final, 820));
    actions.push(common.sayStage(template.final, 'receive', { source: template.manager }));
    actions.push(common.sayStage(template.final, 'final'));
    actions.push(common.pulse(template.final, true));
    return actions;
}

module.exports = {
    buildActions: buildActions
}
