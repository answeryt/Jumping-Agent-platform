'use strict'

var common = require('./flowDemoCommon')

function buildActions(template, taskText) {
    var actions = [
        // 1. Dispatcher announces split start
        common.sayStage(template.dispatcher, 'start'),
        common.pulse(template.dispatcher, true),
        // 2. Split done → wait for charge-and-release
        common.sayStage(template.dispatcher, 'splitDone'),
        // 3. Charge batch jump: hold dispatcher, release to send clones to workers
        common.chargedBatchJump(template.dispatcher, template.workers)
    ];

    // 4. After clones land, workers start analysis
    for (var i = 0; i < template.workers.length; i++) {
        actions.push(common.sayStage(template.workers[i], 'start', { source: template.dispatcher }, 0));
    }
    for (var j = 0; j < template.workers.length; j++) {
        actions.push(common.pulse(template.workers[j], true));
    }

    // 5. All workers done → one charge parallel jump to aggregator
    for (var k = 0; k < template.workers.length; k++) {
        var wId = template.workers[k];
        actions.push(common.sayStage(wId, 'done', { target: template.aggregator }));
    }
    actions.push(common.chargedMergeJump(template.workers, template.aggregator));

    // 6. On aggregator, workers submit results in turn
    for (var r = 0; r < template.workers.length; r++) {
        var resultWorkerId = template.workers[r];
        actions.push(common.sayStage(
            resultWorkerId,
            'result',
            common.resultContext(template, resultWorkerId, taskText, { target: template.aggregator })
        ));
        actions.push(common.sayStage(template.aggregator, 'receive', { source: resultWorkerId }));
    }

    // 7. Aggregator outputs final conclusion
    actions.push(common.sayStage(template.aggregator, 'final'));
    actions.push(common.pulse(template.aggregator, true));
    return actions;
}

module.exports = {
    buildActions: buildActions
}
