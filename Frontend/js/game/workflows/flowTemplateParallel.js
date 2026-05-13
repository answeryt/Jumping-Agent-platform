'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'parallel',
    name: '并行汇总',
    description: '拆分任务，多个 Worker 并行处理，再统一汇总。',
    visualMode: 'parallel_fanout',
    dispatcher: 'dispatcher',
    workers: ['w1', 'w2', 'w3'],
    aggregator: 'aggregator',
    nodes: [
        { id: 'dispatcher', role: 'dispatcher', x: -12, z: 0, label: '任务拆分' },
        { id: 'w1', role: 'worker', x: -2, z: -8, label: '数据 Agent' },
        { id: 'w2', role: 'worker', x: -2, z: 0, label: '代码 Agent' },
        { id: 'w3', role: 'worker', x: -2, z: 8, label: '社区 Agent' },
        { id: 'aggregator', role: 'aggregator', x: 10, z: 0, label: '汇总 Agent' }
    ],
    jumpSequence: ['dispatcher', 'w1', 'aggregator', 'dispatcher', 'w2', 'aggregator', 'dispatcher', 'w3', 'aggregator'],
    dialogues: {
        dispatcher: {
            start: withTask('我先拆分“{task}”，给每个子 Agent 分配不同观察角度。'),
            default: withTask('我继续拆分“{task}”，让不同子 Agent 并行推进。')
        },
        w1: {
            start: withTask('我先分析“{task}”里的数据证据。'),
            done: withTask('数据分析完成，准备汇总给汇总 Agent。'),
            promptNext: function (task, context) {
                return '按压一下，把数据结论发送给 ' + ((context && context.targetLabel) || '汇总 Agent') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的数据结论：关于“' + task + '”，我已经整理出关键指标。');
            }
        },
        w2: {
            start: withTask('我先分析“{task}”里的技术方向。'),
            done: withTask('技术判断完成，准备汇总给汇总 Agent。'),
            promptNext: function (task, context) {
                return '按压一下，把技术结论发送给 ' + ((context && context.targetLabel) || '汇总 Agent') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的技术结论：关于“' + task + '”，我已经归纳出实现路径。');
            }
        },
        w3: {
            start: withTask('我先分析“{task}”的社区讨论和生态反馈。'),
            done: withTask('社区观察完成，准备汇总给汇总 Agent。'),
            promptNext: function (task, context) {
                return '按压一下，把社区反馈发送给 ' + ((context && context.targetLabel) || '汇总 Agent') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的社区结论：关于“' + task + '”，我已经提炼出主要反馈。');
            }
        },
        aggregator: {
            receive: function (task, context) {
                var source = context && context.sourceLabel ? context.sourceLabel : '子 Agent';
                return '已收到 ' + source + ' 的分析，继续汇总其余结果。';
            },
            final: withTask('我已整合全部子 Agent 结果，现在输出“{task}”的完整结论。'),
            default: withTask('我把并行结果合成“{task}”的完整结论。')
        }
    }
}
