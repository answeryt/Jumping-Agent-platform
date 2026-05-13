'use strict'

var common = require('./flowDemoCommon')

function buildActions(template, taskText) {
    var actions = [
        common.sayStage(template.dispatcher, 'start'),
        common.pulse(template.dispatcher, true)
    ];
    for (var i = 0; i < template.workers.length; i++) {
        var workerId = template.workers[i];
        actions.push(common.sayStage(workerId, 'start', { source: template.dispatcher }, 360));
    }
    for (var j = 0; j < template.workers.length; j++) {
        actions.push(common.pulse(template.workers[j], true));
    }
    for (var k = 0; k < template.workers.length; k++) {
        var workerId = template.workers[k];
        actions.push(common.sayStage(workerId, 'done', { target: template.aggregator }));
        actions.push(common.jump(workerId, template.aggregator));
        actions.push(common.sayStage(
            workerId,
            'result',
            common.resultContext(template, workerId, taskText, { target: template.aggregator })
        ));
        actions.push(common.sayStage(template.aggregator, 'receive', { source: workerId }));
    }
    actions.push(common.sayStage(template.aggregator, 'final'));
    actions.push(common.pulse(template.aggregator, true));
    return actions;
}

module.exports = {
    buildActions: buildActions
}
