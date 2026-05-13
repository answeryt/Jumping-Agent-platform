'use strict'

var common = require('./flowDemoCommon')

function buildActions(template, taskText) {
    return common.buildLinearJumpActions(template, taskText);
}

module.exports = {
    buildActions: buildActions
}
