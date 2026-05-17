'use strict'

var common = require('./flowDemoCommon')

function buildActions(template, taskText) {
    var branchId = selectBranch(template, taskText);
    var actions = [
        common.sayStage(template.dispatcher, 'start'),
        common.pulse(template.dispatcher, true),
        common.sayStage(template.dispatcher, 'route', { target: branchId }, 980),
        common.jump(template.dispatcher, branchId, 820),
        common.sayStage(branchId, 'start'),
        common.pulse(branchId),
        common.sayStage(branchId, 'done', { target: template.result }),
        common.jump(branchId, template.result, 880),
        common.sayStage(
            branchId,
            'result',
            common.resultContext(template, branchId, taskText, { target: template.result })
        ),
        common.sayStage(template.result, 'receive', { source: branchId }),
        common.sayStage(template.result, 'final'),
        common.pulse(template.result, true)
    ];
    return actions;
}

function selectBranch(template, taskText) {
    var branches = template.branches || [];
    var normalized = (taskText || '').toLowerCase();
    if (!branches.length) {
        return null;
    }
    // Bilingual keywords (EN + legacy ZH) for branch routing from free-text tasks
    if (/risk|law|legal|合规|法律|风险|安全/.test(normalized) && branches.indexOf('legal') !== -1) {
        return 'legal';
    }
    if (/business|market|finance|money|商业|市场|增长|收入|成本/.test(normalized) && branches.indexOf('finance') !== -1) {
        return 'finance';
    }
    return branches.indexOf('tech') !== -1 ? 'tech' : branches[0];
}

module.exports = {
    buildActions: buildActions
}
