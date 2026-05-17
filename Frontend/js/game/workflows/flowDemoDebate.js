'use strict'

var common = require('./flowDemoCommon')

function buildActions(template, taskText) {
    var actions = [
        common.sayStage(template.moderator, 'start'),
        common.pulse(template.moderator, true)
    ];
    for (var i = 0; i < template.participants.length; i++) {
        var participantId = template.participants[i];
        actions.push(common.sayStage(template.moderator, 'handoff', { target: participantId }, 980));
        actions.push(common.jump(template.moderator, participantId, 820));
        actions.push(common.sayStage(participantId, 'start', { source: template.moderator }));
        actions.push(common.pulse(participantId));
        actions.push(common.sayStage(participantId, 'response'));
        actions.push(common.sayStage(participantId, 'done', { target: template.moderator }));
        actions.push(common.jump(participantId, template.moderator, 820));
        actions.push(common.sayStage(
            participantId,
            'result',
            common.resultContext(template, participantId, taskText, { target: template.moderator })
        ));
        actions.push(common.sayStage(template.moderator, 'receive', { source: participantId }));
    }
    actions.push(common.sayStage(template.moderator, 'final'));
    actions.push(common.pulse(template.moderator, true));
    return actions;
}

module.exports = {
    buildActions: buildActions
}
