'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'router',
    name: '条件路由',
    description: 'Dispatcher 判断路线后，把任务交给目标分支。',
    visualMode: 'router_branch',
    dispatcher: 'dispatcher',
    branches: ['tech', 'finance', 'legal'],
    result: 'result',
    nodes: [
        { id: 'dispatcher', role: 'dispatcher', x: -10, z: 0, label: '路由判断' },
        { id: 'tech', role: 'agent', x: 0, z: -8, label: '技术分支' },
        { id: 'finance', role: 'agent', x: 0, z: 0, label: '商业分支' },
        { id: 'legal', role: 'agent', x: 0, z: 8, label: '风险分支' },
        { id: 'result', role: 'agent', x: 10, z: 0, label: '结果汇总' }
    ],
    jumpSequence: ['dispatcher', 'tech', 'result', 'dispatcher', 'finance', 'result', 'dispatcher', 'legal', 'result'],
    dialogues: {
        dispatcher: {
            start: withTask('我先判断“{task}”应该进入哪条分析分支。'),
            route: function (task, context) {
                return '我判断“' + task + '”当前更适合交给 ' + ((context && context.targetLabel) || '目标分支') + '。';
            },
            promptNext: function (task, context) {
                return '按压一下，把路由结果送到 ' + ((context && context.targetLabel) || '目标分支') + '。';
            },
            default: withTask('我先判断“{task}”应该进入哪条分析分支。')
        },
        tech: {
            start: withTask('“{task}”更像技术趋势问题，我先从技术分支分析。'),
            done: withTask('技术分析完成，准备提交给结果汇总节点。'),
            promptNext: function (task, context) {
                return '按压一下，把技术分支结论提交给 ' + ((context && context.targetLabel) || '结果汇总') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的技术分支结论：关于“' + task + '”，技术路径与趋势已明确。');
            }
        },
        finance: {
            start: withTask('我补充“{task}”背后的增长和采用价值。'),
            done: withTask('商业分析完成，准备提交给结果汇总节点。'),
            promptNext: function (task, context) {
                return '按压一下，把商业分支结论提交给 ' + ((context && context.targetLabel) || '结果汇总') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的商业分支结论：关于“' + task + '”，增长空间与采用价值已整理。');
            }
        },
        legal: {
            start: withTask('我检查“{task}”可能带来的风险和限制。'),
            done: withTask('风险审查完成，准备提交给结果汇总节点。'),
            promptNext: function (task, context) {
                return '按压一下，把风险分支结论提交给 ' + ((context && context.targetLabel) || '结果汇总') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的风险分支结论：关于“' + task + '”，主要限制与风险点已提炼。');
            }
        },
        result: {
            receive: function (task, context) {
                return '已收到 ' + ((context && context.sourceLabel) || '分支 Agent') + ' 的判断，继续汇总整体结论。';
            },
            final: withTask('我把各分支对“{task}”的判断合成答案。'),
            default: withTask('我把各分支对“{task}”的判断合成答案。')
        }
    }
}
