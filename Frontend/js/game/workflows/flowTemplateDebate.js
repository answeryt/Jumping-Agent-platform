'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'debate',
    name: 'Multi-party debate',
    description: 'Participants take turns; the moderator checks for consensus.',
    visualMode: 'debate_round',
    participants: ['optimist', 'pessimist', 'realist'],
    moderator: 'moderator',
    nodes: [
        { id: 'moderator', role: 'moderator', x: 0, z: 3, label: 'Moderator' },
        { id: 'optimist', role: 'participant', x: -8, z: -6, label: 'Optimist' },
        { id: 'pessimist', role: 'participant', x: 0, z: -9, label: 'Skeptic' },
        { id: 'realist', role: 'participant', x: 8, z: -6, label: 'Realist' }
    ],
    jumpSequence: [],
    dialogues: {
        optimist: {
            start: withTask('From an opportunity angle on "{task}": which trends are worth betting on?'),
            response: withTask('One more point: on the upside, "{task}" still has room to grow.'),
            result: function (task, context) {
                return (context && context.result) || ('My summary: for "' + task + '", the opportunity window remains open.');
            },
            done: withTask('Optimist view is ready to send to the moderator.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send the optimist view to ' + ((context && context.targetLabel) || 'Moderator') + '.';
            }
        },
        pessimist: {
            start: withTask('I question "{task}": is the hype only short-term noise?'),
            response: withTask('Risk reminder: without sustained data, "{task}" may be a passing trend.'),
            result: function (task, context) {
                return (context && context.result) || ('My summary: for "' + task + '", watch for hype and short-term noise.');
            },
            done: withTask('Skeptic view is ready to send to the moderator.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send the skeptic view to ' + ((context && context.targetLabel) || 'Moderator') + '.';
            }
        },
        realist: {
            start: withTask('Balanced take on "{task}": data, ecosystem, and real-world fit.'),
            response: withTask('Balancing again: judge "{task}" on growth, risk, and feasibility together.'),
            result: function (task, context) {
                return (context && context.result) || ('My summary: for "' + task + '", an evidence-based neutral view is needed.');
            },
            done: withTask('Realist view is ready to send to the moderator.'),
            promptNext: function (task, context) {
                return 'Hold to jump and send the realist view to ' + ((context && context.targetLabel) || 'Moderator') + '.';
            }
        },
        moderator: {
            start: withTask('Topic for this round: "{task}". Please share from different stances.'),
            handoff: function (task, context) {
                return 'Passing the topic "' + task + '" to ' + ((context && context.targetLabel) || 'the next participant') + '.';
            },
            receive: function (task, context) {
                return 'Received input from ' + ((context && context.sourceLabel) || 'participant') + '; listening to the next view.';
            },
            promptNext: function (task, context) {
                return 'Hold to jump and pass the topic to ' + ((context && context.targetLabel) || 'the next participant') + '.';
            },
            final: withTask('I summarize the debate into consensus on "{task}".'),
            default: withTask('I summarize the debate into consensus on "{task}".')
        }
    }
}
