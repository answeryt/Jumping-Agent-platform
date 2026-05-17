'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'loop',
    name: 'Review loop',
    description: 'Executor produces output; evaluator reviews and may send work back.',
    visualMode: 'loop_review',
    nodes: [
        { id: 'executor', role: 'executor', x: -5, z: 0, label: 'Executor' },
        { id: 'evaluator', role: 'evaluator', x: 5, z: 0, label: 'Evaluator' },
        { id: 'approved', role: 'agent', x: 5, z: -9, label: 'Approved' }
    ],
    jumpSequence: ['executor', 'evaluator', 'executor', 'evaluator', 'approved'],
    dialogues: {
        executor: {
            start: withTask('I will draft the first answer for "{task}".'),
            revise: withTask('I will revise the answer for "{task}" based on review feedback.'),
            done: withTask('Current draft is ready for the evaluator.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send the draft to ' + ((context && context.targetLabel) || 'Evaluator') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Current draft for "' + task + '" is updated and ready for review.');
            },
            default: withTask('I keep refining the answer for "{task}" before resubmitting.')
        },
        evaluator: {
            start: withTask('I will check whether the answer for "{task}" is sound.'),
            feedback: withTask('There is room to improve; sending feedback back to the executor.'),
            approve: withTask('The answer for "{task}" passes; ready for final output.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send the review to ' + ((context && context.targetLabel) || 'the next node') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Review conclusion for "' + task + '" is ready.');
            }
        },
        approved: {
            receive: function (task, context) {
                return 'Approval received from ' + ((context && context.sourceLabel) || 'Evaluator') + '; preparing final output.';
            },
            final: withTask('Quality approved; outputting the answer for "{task}".'),
            default: withTask('Quality approved; outputting the answer for "{task}".')
        }
    }
}
