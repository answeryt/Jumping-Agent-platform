'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'hierarchical',
    name: 'Hierarchical delegation',
    description: 'Manager breaks down work and delegates to workers.',
    visualMode: 'hierarchical_delegate',
    manager: 'manager',
    workers: ['dev', 'tester', 'designer'],
    final: 'final',
    nodes: [
        { id: 'manager', role: 'manager', x: 0, z: -10, label: 'Manager' },
        { id: 'dev', role: 'worker', x: -10, z: 0, label: 'Researcher' },
        { id: 'tester', role: 'worker', x: 0, z: 0, label: 'Verifier' },
        { id: 'designer', role: 'worker', x: 10, z: 0, label: 'Writer' },
        { id: 'final', role: 'aggregator', x: 0, z: 9, label: 'Final report' }
    ],
    jumpSequence: ['manager', 'dev', 'manager', 'tester', 'manager', 'designer', 'final'],
    dialogues: {
        manager: {
            start: withTask('I will break down "{task}" and delegate sub-tasks.'),
            delegate: function (task, context) {
                return 'I assign part of "' + task + '" to ' + ((context && context.targetLabel) || 'sub-agent') + '.';
            },
            promptNext: function (task, context) {
                return 'Hold to jump and send delegation to ' + ((context && context.targetLabel) || 'the target node') + '.';
            },
            receive: function (task, context) {
                return 'Received progress from ' + ((context && context.sourceLabel) || 'sub-agent') + '; moving to the next step.';
            },
            default: withTask('I continue breaking down "{task}" and delegating to the next sub-agent.')
        },
        dev: {
            start: withTask('I will research core material for "{task}".'),
            done: withTask('Research done; ready to submit to the final report node.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send research back to ' + ((context && context.targetLabel) || 'Manager') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Research conclusion: core facts for "' + task + '" are organized.');
            }
        },
        tester: {
            start: withTask('I will verify evidence for "{task}".'),
            done: withTask('Verification done; ready to submit results.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send verification to ' + ((context && context.targetLabel) || 'Manager') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Verification conclusion: key evidence for "' + task + '" is checked.');
            }
        },
        designer: {
            start: withTask('I will turn "{task}" into clearer wording.'),
            done: withTask('Writing done; ready for the final report.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send the write-up to ' + ((context && context.targetLabel) || 'Manager') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Writing conclusion: content for "' + task + '" is clear and structured.');
            }
        },
        final: {
            receive: function (task, context) {
                return 'Received team summary from ' + ((context && context.sourceLabel) || 'Manager') + '; preparing final output.';
            },
            final: withTask('Team output is merged; delivering the final report for "{task}".'),
            default: withTask('I merge the team work on "{task}".')
        }
    }
}
