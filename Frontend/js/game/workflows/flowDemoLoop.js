'use strict'

var common = require('./flowDemoCommon')

function buildActions(template, taskText) {
    var executor = 'executor';
    var evaluator = 'evaluator';
    var approved = 'approved';
    return [
        common.sayStage(executor, 'start'),
        common.pulse(executor),
        common.sayStage(executor, 'done', { target: evaluator }),
        common.jump(executor, evaluator, 860),
        common.sayStage(
            executor,
            'result',
            common.resultContext(template, executor, taskText, { target: evaluator })
        ),
        common.sayStage(evaluator, 'start', { source: executor }),
        common.pulse(evaluator),
        common.sayStage(evaluator, 'feedback', { target: executor }),
        common.jump(evaluator, executor, 860),
        common.sayStage(
            evaluator,
            'result',
            common.resultContext(template, evaluator, taskText, { target: executor })
        ),
        common.sayStage(executor, 'revise', { source: evaluator }),
        common.pulse(executor),
        common.sayStage(executor, 'done', { target: evaluator }),
        common.jump(executor, evaluator, 860),
        common.sayStage(evaluator, 'approve', { target: approved }),
        common.jump(evaluator, approved, 860),
        common.sayStage(approved, 'receive', { source: evaluator }),
        common.sayStage(approved, 'final'),
        common.pulse(approved, true)
    ];
}

module.exports = {
    buildActions: buildActions
}
