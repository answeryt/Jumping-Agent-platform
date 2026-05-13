'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'sequential',
    name: '顺序链',
    description: 'Agent 按固定顺序依次交接任务。',
    visualMode: 'linear_jump',
    nodes: [
        { id: 'a', role: 'agent', x: -12, z: 0, label: '需求理解' },
        { id: 'b', role: 'agent', x: -4, z: 0, label: '信息收集' },
        { id: 'c', role: 'agent', x: 4, z: 0, label: '分析整理' },
        { id: 'd', role: 'agent', x: 12, z: 0, label: '输出报告' }
    ],
    jumpSequence: ['a', 'b', 'c', 'd'],
    dialogues: {
        a: {
            start: withTask('我先理解“{task}”的目标和边界。'),
            handoff: function (task, context) {
                return '我已梳理好“' + task + '”的目标与约束，现在正式交接给 ' + ((context && context.targetLabel) || '下一位 Agent') + '。';
            },
            promptNext: function (task, context) {
                return '按压一下，让我跳到 ' + ((context && context.targetLabel) || '下一位 Agent') + '，开始交接。';
            },
            done: function (task, context) {
                return '需求已经梳理清楚，准备交接给 ' + ((context && context.targetLabel) || '下一位 Agent') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的需求结论：关于“' + task + '”，目标与约束已经明确。');
            },
            default: function (task, context) {
                return '按压一下，让我跳到 ' + ((context && context.targetLabel) || '下一位 Agent') + '，开始交接。';
            }
        },
        b: {
            start: withTask('我先围绕“{task}”收集线索。'),
            receive: function (task, context) {
                return '我已收到 ' + ((context && context.sourceLabel) || '上一位 Agent') + ' 的任务背景，现在开始信息收集。';
            },
            handoff: function (task, context) {
                return '信息已经收集完成，我准备把线索正式交接给 ' + ((context && context.targetLabel) || '下一位 Agent') + '。';
            },
            promptNext: function (task, context) {
                return '按压一下，让信息收集结果跳转给 ' + ((context && context.targetLabel) || '下一位 Agent') + '。';
            },
            done: function (task, context) {
                return '线索已经收集完成，准备转交给 ' + ((context && context.targetLabel) || '下一位 Agent') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的收集结果：关于“' + task + '”，关键线索已经整理出来。');
            }
        },
        c: {
            start: withTask('我把“{task}”拆成趋势、证据和结论。'),
            receive: function (task, context) {
                return '我已收到 ' + ((context && context.sourceLabel) || '上一位 Agent') + ' 提供的线索，开始分析整理。';
            },
            handoff: function (task, context) {
                return '分析整理完成，我准备把归纳结果交接给 ' + ((context && context.targetLabel) || '下一位 Agent') + '。';
            },
            promptNext: function (task, context) {
                return '按压一下，让分析结果继续跳向 ' + ((context && context.targetLabel) || '下一位 Agent') + '。';
            },
            done: function (task, context) {
                return '分析整理完成，准备同步给 ' + ((context && context.targetLabel) || '下一位 Agent') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的分析结果：关于“' + task + '”，趋势、证据和判断已归纳完成。');
            }
        },
        d: {
            receive: function (task, context) {
                return '已收到 ' + ((context && context.sourceLabel) || '上一位 Agent') + ' 的整理结果，准备输出最终答案。';
            },
            final: withTask('我给出“{task}”的最终答案。'),
            default: withTask('我给出“{task}”的最终答案。')
        }
    }
}
