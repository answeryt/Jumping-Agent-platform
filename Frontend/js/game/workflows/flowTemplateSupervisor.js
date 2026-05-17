'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'supervisor',
    name: 'Supervisor orchestration',
    description: 'Supervisor watches all agents and dispatches the next step.',
    visualMode: 'supervisor_dispatch',
    supervisor: 'supervisor',
    agents: ['planner', 'researcher', 'builder', 'reviewer'],
    nodes: [
        { id: 'supervisor', role: 'manager', x: 0, z: -10, label: 'Supervisor' },
        { id: 'planner', role: 'agent', x: -9, z: -1, label: 'Planner' },
        { id: 'researcher', role: 'agent', x: 9, z: -1, label: 'Researcher' },
        { id: 'builder', role: 'agent', x: -6, z: 8, label: 'Builder' },
        { id: 'reviewer', role: 'evaluator', x: 6, z: 8, label: 'Reviewer' }
    ],
    jumpSequence: ['supervisor', 'planner', 'supervisor', 'researcher', 'supervisor', 'builder', 'reviewer', 'supervisor'],
    dialogues: {
        supervisor: {
            start: withTask('I will survey the pipeline and decide who should handle "{task}" first.'),
            delegate: function (task, context) {
                return 'Next I assign "' + task + '" to ' + ((context && context.targetLabel) || 'the target agent') + '.';
            },
            promptNext: function (task, context) {
                return 'Hold to jump and send dispatch instructions to ' + ((context && context.targetLabel) || 'the target agent') + '.';
            },
            receive: function (task, context) {
                return 'Received results from ' + ((context && context.sourceLabel) || 'agent') + '; deciding the next move.';
            },
            final: withTask('All inputs are in; here is the final orchestration conclusion for "{task}".'),
            default: withTask('I keep watching the pipeline and deciding who handles "{task}" next.')
        },
        planner: {
            start: withTask('I will plan the execution path for "{task}".'),
            done: withTask('Planning done; sending the route back to Supervisor.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send the plan to ' + ((context && context.targetLabel) || 'Supervisor') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Planning result: execution route for "' + task + '" is ready.');
            }
        },
        researcher: {
            start: withTask('I will gather external information needed for "{task}".'),
            done: withTask('Research done; sending results back to Supervisor.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send research to ' + ((context && context.targetLabel) || 'Supervisor') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Research result: external info for "' + task + '" is collected.');
            }
        },
        builder: {
            start: withTask('I will generate a first draft for "{task}".'),
            done: withTask('Draft ready; submitting to Supervisor.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send the draft to ' + ((context && context.targetLabel) || 'Supervisor') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Draft for "' + task + '" is ready.');
            }
        },
        reviewer: {
            start: withTask('I will review gaps in the answer for "{task}".'),
            done: withTask('Review done; sending issues and suggestions to Supervisor.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send review notes to ' + ((context && context.targetLabel) || 'Supervisor') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Review for "' + task + '": risks and improvements are listed.');
            }
        }
    }
}
