'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'sequential',
    name: 'Sequential chain',
    description: 'Agents hand off the task in a fixed order.',
    visualMode: 'linear_jump',
    nodes: [
        { id: 'a', role: 'agent', x: -12, z: 0, label: 'Requirements' },
        { id: 'b', role: 'agent', x: -4, z: 0, label: 'Research' },
        { id: 'c', role: 'agent', x: 4, z: 0, label: 'Analysis' },
        { id: 'd', role: 'agent', x: 12, z: 0, label: 'Report' }
    ],
    jumpSequence: ['a', 'b', 'c', 'd'],
    dialogues: {
        a: {
            start: withTask('I will clarify goals and scope for "{task}".'),
            handoff: function (task, context) {
                return 'Goals and constraints for "' + task + '" are clear; handing off to ' + ((context && context.targetLabel) || 'the next agent') + '.';
            },
            promptNext: function (task, context) {
                return 'Hold to jump to ' + ((context && context.targetLabel) || 'the next agent') + ' and hand off.';
            },
            done: function (task, context) {
                return 'Requirements are ready to hand off to ' + ((context && context.targetLabel) || 'the next agent') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Requirements summary: goals and constraints for "' + task + '" are defined.');
            },
            default: function (task, context) {
                return 'Hold to jump to ' + ((context && context.targetLabel) || 'the next agent') + ' and hand off.';
            }
        },
        b: {
            start: withTask('I will gather clues around "{task}".'),
            receive: function (task, context) {
                return 'Received context from ' + ((context && context.sourceLabel) || 'the previous agent') + '; starting research.';
            },
            handoff: function (task, context) {
                return 'Research is done; handing clues to ' + ((context && context.targetLabel) || 'the next agent') + '.';
            },
            promptNext: function (task, context) {
                return 'Hold to jump and send research results to ' + ((context && context.targetLabel) || 'the next agent') + '.';
            },
            done: function (task, context) {
                return 'Clues are ready to pass to ' + ((context && context.targetLabel) || 'the next agent') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Research summary: key clues for "' + task + '" are collected.');
            }
        },
        c: {
            start: withTask('I will break "{task}" into trends, evidence, and conclusions.'),
            receive: function (task, context) {
                return 'Received clues from ' + ((context && context.sourceLabel) || 'the previous agent') + '; starting analysis.';
            },
            handoff: function (task, context) {
                return 'Analysis done; handing synthesis to ' + ((context && context.targetLabel) || 'the next agent') + '.';
            },
            promptNext: function (task, context) {
                return 'Hold to jump and send analysis to ' + ((context && context.targetLabel) || 'the next agent') + '.';
            },
            done: function (task, context) {
                return 'Analysis ready to sync with ' + ((context && context.targetLabel) || 'the next agent') + '.';
            },
            result: function (task, context) {
                return (context && context.result) || ('Analysis summary: trends, evidence, and judgment for "' + task + '" are ready.');
            }
        },
        d: {
            receive: function (task, context) {
                return 'Received synthesis from ' + ((context && context.sourceLabel) || 'the previous agent') + '; preparing final answer.';
            },
            final: withTask('Here is the final answer for "{task}".'),
            default: withTask('Here is the final answer for "{task}".')
        }
    }
}
