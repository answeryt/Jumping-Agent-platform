'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'debate',
    name: '多方讨论',
    description: '多个参与者轮流发言，由主持人判断是否达成共识。',
    visualMode: 'debate_round',
    participants: ['optimist', 'pessimist', 'realist'],
    moderator: 'moderator',
    nodes: [
        { id: 'moderator', role: 'moderator', x: 0, z: 3, label: '主持人' },
        { id: 'optimist', role: 'participant', x: -8, z: -6, label: '乐观派' },
        { id: 'pessimist', role: 'participant', x: 0, z: -9, label: '质疑派' },
        { id: 'realist', role: 'participant', x: 8, z: -6, label: '现实派' }
    ],
    jumpSequence: [],
    dialogues: {
        optimist: {
            start: withTask('我先从机会角度看“{task}”：哪些趋势值得下注？'),
            response: withTask('我补充一点：从机会面看，“{task}”仍有进一步放大的空间。'),
            result: function (task, context) {
                return (context && context.result) || ('我的立场总结是：关于“' + task + '”，机会窗口依然存在。');
            }
        },
        pessimist: {
            start: withTask('我质疑“{task}”：热度是否只是短期噪声？'),
            response: withTask('我继续提醒风险：如果缺少持续数据支撑，“{task}”可能只是阶段性热度。'),
            result: function (task, context) {
                return (context && context.result) || ('我的立场总结是：关于“' + task + '”，仍需警惕泡沫和短期噪声。');
            }
        },
        realist: {
            start: withTask('我折中判断“{task}”：看数据、生态和落地场景。'),
            response: withTask('我再平衡一下：评价“{task}”需要同时看增长、风险和落地条件。'),
            result: function (task, context) {
                return (context && context.result) || ('我的立场总结是：关于“' + task + '”，需要基于证据做中性判断。');
            }
        },
        moderator: {
            start: withTask('本轮议题是“{task}”，请各位从不同立场展开讨论。'),
            receive: function (task, context) {
                return '已收到 ' + ((context && context.sourceLabel) || '参与方') + ' 的观点，继续听取下一位意见。';
            },
            final: withTask('我总结辩论，形成“{task}”的共识。'),
            default: withTask('我总结辩论，形成“{task}”的共识。')
        }
    }
}
