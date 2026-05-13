'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'loop',
    name: '循环反思',
    description: '执行者产出结果，评估者反馈，不通过则回到执行者。',
    visualMode: 'loop_review',
    nodes: [
        { id: 'executor', role: 'executor', x: -5, z: 0, label: '执行 Agent' },
        { id: 'evaluator', role: 'evaluator', x: 5, z: 0, label: '评估 Agent' },
        { id: 'approved', role: 'agent', x: 5, z: -9, label: '通过' }
    ],
    jumpSequence: ['executor', 'evaluator', 'executor', 'evaluator', 'approved'],
    dialogues: {
        executor: {
            start: withTask('我先为“{task}”生成第一版答案。'),
            revise: withTask('我根据评估反馈继续修正“{task}”的答案。'),
            done: withTask('当前版本已完成，准备交给评估 Agent 复核。'),
            promptNext: function (task, context) {
                return '按压一下，把当前版本交给 ' + ((context && context.targetLabel) || '评估 Agent') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的当前版本：关于“' + task + '”，答案已更新并可进入复核。');
            },
            default: withTask('我继续完善“{task}”的答案，准备再次提交评估。')
        },
        evaluator: {
            start: withTask('我检查“{task}”的答案是否可信。'),
            feedback: withTask('我发现还可继续优化，准备把反馈返回给执行 Agent。'),
            approve: withTask('我确认“{task}”的答案已经通过，可以进入最终输出。'),
            promptNext: function (task, context) {
                return '按压一下，把评估判断返回给 ' + ((context && context.targetLabel) || '下一节点') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的评估结论：关于“' + task + '”，我已给出复核判断。');
            }
        },
        approved: {
            receive: function (task, context) {
                return '已收到 ' + ((context && context.sourceLabel) || '评估 Agent') + ' 的通过信号，准备输出最终结果。';
            },
            final: withTask('质量通过，可以输出“{task}”的答案。'),
            default: withTask('质量通过，可以输出“{task}”的答案。')
        }
    }
}
