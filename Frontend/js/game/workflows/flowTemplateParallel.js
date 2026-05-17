'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'parallel',
    name: 'Parallel merge',
    description: 'Split work across workers in parallel, then merge results.',
    visualMode: 'parallel_fanout',
    dispatcher: 'dispatcher',
    workers: ['w1', 'w2', 'w3'],
    aggregator: 'aggregator',
    nodes: [
        { id: 'dispatcher', role: 'dispatcher', x: -12, z: 0, label: 'Task split' },
        { id: 'w1', role: 'worker', x: -2, z: -8, label: 'Data agent' },
        { id: 'w2', role: 'worker', x: -2, z: 0, label: 'Code agent' },
        { id: 'w3', role: 'worker', x: -2, z: 8, label: 'Community agent' },
        { id: 'aggregator', role: 'aggregator', x: 10, z: 0, label: 'Aggregator' }
    ],
    jumpSequence: ['dispatcher', 'w1', 'aggregator', 'dispatcher', 'w2', 'aggregator', 'dispatcher', 'w3', 'aggregator'],
    dialogues: {
        dispatcher: {
            start: withTask('I will split "{task}" and assign each sub-agent a different angle.'),
            splitDone: withTask('Split complete; all sub-tasks for "{task}" are ready.'),
            promptNext: function (task, context) {
                var targetLabel = (context && context.targetLabel) || 'Aggregator';
                return 'Hold to jump and send sub-task conclusions for "' + task + '" to ' + targetLabel + '.';
            },
            default: withTask('I continue splitting "{task}" so sub-agents can work in parallel.')
        },
        w1: {
            start: withTask('I will analyze data evidence for "{task}".'),
            done: withTask('Data analysis done; ready to merge with the aggregator.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send data conclusions to ' + ((context && context.targetLabel) || 'Aggregator') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('My data conclusion: for "' + task + '", key metrics are ready.');
            }
        },
        w2: {
            start: withTask('I will analyze the technical direction of "{task}".'),
            done: withTask('Technical review done; ready to merge with the aggregator.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send technical conclusions to ' + ((context && context.targetLabel) || 'Aggregator') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('My technical conclusion: for "' + task + '", an implementation path is outlined.');
            }
        },
        w3: {
            start: withTask('I will review community discussion and ecosystem feedback for "{task}".'),
            done: withTask('Community review done; ready to merge with the aggregator.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send community feedback to ' + ((context && context.targetLabel) || 'Aggregator') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('My community conclusion: for "' + task + '", main feedback is summarized.');
            }
        },
        aggregator: {
            receive: function (task, context) {
                var source = context && context.sourceLabel ? context.sourceLabel : 'Sub-agent';
                return 'Received analysis from ' + source + '; continuing to merge other results.';
            },
            final: withTask('All sub-agent results are merged; outputting the full conclusion for "{task}".'),
            default: withTask('I synthesize parallel results into the full conclusion for "{task}".')
        }
    }
}
