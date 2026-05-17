'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'router',
    name: 'Conditional routing',
    description: 'Dispatcher picks a branch and hands the task to it.',
    visualMode: 'router_branch',
    dispatcher: 'dispatcher',
    branches: ['tech', 'finance', 'legal'],
    result: 'result',
    nodes: [
        { id: 'dispatcher', role: 'dispatcher', x: -10, z: 0, label: 'Routing' },
        { id: 'tech', role: 'agent', x: 0, z: -8, label: 'Tech branch' },
        { id: 'finance', role: 'agent', x: 0, z: 0, label: 'Business branch' },
        { id: 'legal', role: 'agent', x: 0, z: 8, label: 'Risk branch' },
        { id: 'result', role: 'agent', x: 10, z: 0, label: 'Merge results' }
    ],
    jumpSequence: ['dispatcher', 'tech', 'result', 'dispatcher', 'finance', 'result', 'dispatcher', 'legal', 'result'],
    dialogues: {
        dispatcher: {
            start: withTask('I will decide which analysis branch "{task}" should enter.'),
            route: function (task, context) {
                return 'I route "' + task + '" to ' + ((context && context.targetLabel) || 'the target branch') + '.';
            },
            promptNext: function (task, context) {
                return 'Hold to jump and send the routing decision to ' + ((context && context.targetLabel) || 'the target branch') + '.';
            },
            default: withTask('I will decide which analysis branch "{task}" should enter.')
        },
        tech: {
            start: withTask('"{task}" looks like a tech trend question; analyzing from the tech branch.'),
            done: withTask('Tech analysis done; ready to submit to the merge node.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send tech conclusions to ' + ((context && context.targetLabel) || 'Merge results') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Tech branch conclusion: path and trends for "' + task + '" are clear.');
            }
        },
        finance: {
            start: withTask('I will cover growth and adoption value behind "{task}".'),
            done: withTask('Business analysis done; ready to submit to the merge node.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send business conclusions to ' + ((context && context.targetLabel) || 'Merge results') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Business branch conclusion: growth and adoption for "' + task + '" are summarized.');
            }
        },
        legal: {
            start: withTask('I will check risks and constraints around "{task}".'),
            done: withTask('Risk review done; ready to submit to the merge node.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send risk conclusions to ' + ((context && context.targetLabel) || 'Merge results') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Risk branch conclusion: main limits and risks for "' + task + '" are listed.');
            }
        },
        result: {
            receive: function (task, context) {
                return 'Received judgment from ' + ((context && context.sourceLabel) || 'branch agent') + '; continuing to merge.';
            },
            final: withTask('I synthesize branch judgments on "{task}" into the final answer.'),
            default: withTask('I synthesize branch judgments on "{task}" into the final answer.')
        }
    }
}
