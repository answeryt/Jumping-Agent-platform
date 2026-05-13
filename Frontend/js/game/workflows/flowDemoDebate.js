'use strict'

var common = require('./flowDemoCommon')

function buildActions(template, taskText) {
    var actions = [
        common.sayStage(template.moderator, 'start')
    ];
    for (var i = 0; i < template.participants.length; i++) {
        var participantId = template.participants[i];
        actions.push(common.sayStage(participantId, 'start'));
        actions.push(common.pulse(participantId));
        actions.push(common.sayStage(participantId, 'response'));
        actions.push(common.sayStage(
            participantId,
            'result',
            common.resultContext(template, participantId, taskText)
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
