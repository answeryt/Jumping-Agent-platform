'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'hierarchical',
    name: '层级委派',
    description: 'Manager 分解任务并委派给下级 Worker。',
    visualMode: 'hierarchical_delegate',
    manager: 'manager',
    workers: ['dev', 'tester', 'designer'],
    final: 'final',
    nodes: [
        { id: 'manager', role: 'manager', x: 0, z: -10, label: 'Manager' },
        { id: 'dev', role: 'worker', x: -10, z: 0, label: '研究员' },
        { id: 'tester', role: 'worker', x: 0, z: 0, label: '验证员' },
        { id: 'designer', role: 'worker', x: 10, z: 0, label: '表达员' },
        { id: 'final', role: 'aggregator', x: 0, z: 9, label: '最终汇报' }
    ],
    jumpSequence: ['manager', 'dev', 'manager', 'tester', 'manager', 'designer', 'final'],
    dialogues: {
        manager: {
            start: withTask('我先拆解“{task}”，准备逐个委派子任务。'),
            delegate: function (task, context) {
                return '我把“' + task + '”中的一部分交给 ' + ((context && context.targetLabel) || '子 Agent') + '。';
            },
            promptNext: function (task, context) {
                return '按压一下，把委派指令送到 ' + ((context && context.targetLabel) || '目标节点') + '。';
            },
            receive: function (task, context) {
                return '已收到 ' + ((context && context.sourceLabel) || '子 Agent') + ' 的阶段汇报，继续推进下一步。';
            },
            default: withTask('我继续拆解“{task}”，准备委派下一位子 Agent。')
        },
        dev: {
            start: withTask('我先研究“{task}”的核心资料。'),
            done: withTask('资料研究完成，准备向最终汇报节点提交结论。'),
            promptNext: function (task, context) {
                return '按压一下，把研究汇报返回给 ' + ((context && context.targetLabel) || 'Manager') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('我的研究结论是：关于“' + task + '”，核心信息已经整理完成。');
            }
        },
        tester: {
            start: withTask('我先验证“{task}”相关证据是否可靠。'),
            done: withTask('验证完成，准备把校验结果提交上去。'),
            promptNext: function (task, context) {
                return '按压一下，把验证汇报返回给 ' + ((context && context.targetLabel) || 'Manager') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('我的验证结论是：关于“' + task + '”，关键证据已完成校验。');
            }
        },
        designer: {
            start: withTask('我先把“{task}”整理成更易理解的表达。'),
            done: withTask('表达整理完成，准备交付最终汇报。'),
            promptNext: function (task, context) {
                return '按压一下，把表达汇报返回给 ' + ((context && context.targetLabel) || 'Manager') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('我的表达结论是：关于“' + task + '”，内容已整理成清晰版本。');
            }
        },
        final: {
            receive: function (task, context) {
                return '已收到 ' + ((context && context.sourceLabel) || 'Manager') + ' 的团队汇总，准备最终输出。';
            },
            final: withTask('我已汇总团队成果，现在形成“{task}”的最终汇报。'),
            default: withTask('我汇总团队对“{task}”的成果。')
        }
    }
}
