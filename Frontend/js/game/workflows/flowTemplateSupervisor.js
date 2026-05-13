'use strict'

var withTask = require('./flowTemplateCommon').withTask

module.exports = {
    id: 'supervisor',
    name: '监督编排',
    description: 'Supervisor 统一观察多个 Agent，并按需调度下一步。',
    visualMode: 'supervisor_dispatch',
    supervisor: 'supervisor',
    agents: ['planner', 'researcher', 'builder', 'reviewer'],
    nodes: [
        { id: 'supervisor', role: 'manager', x: 0, z: -10, label: 'Supervisor' },
        { id: 'planner', role: 'agent', x: -9, z: -1, label: '规划 Agent' },
        { id: 'researcher', role: 'agent', x: 9, z: -1, label: '研究 Agent' },
        { id: 'builder', role: 'agent', x: -6, z: 8, label: '生成 Agent' },
        { id: 'reviewer', role: 'evaluator', x: 6, z: 8, label: '审查 Agent' }
    ],
    jumpSequence: ['supervisor', 'planner', 'supervisor', 'researcher', 'supervisor', 'builder', 'reviewer', 'supervisor'],
    dialogues: {
        supervisor: {
            start: withTask('我先观察全局，决定“{task}”应该先调度谁。'),
            delegate: function (task, context) {
                return '下一步我把“' + task + '”交给 ' + ((context && context.targetLabel) || '目标 Agent') + '。';
            },
            promptNext: function (task, context) {
                return '按压一下，把调度指令送到 ' + ((context && context.targetLabel) || '目标 Agent') + '。';
            },
            receive: function (task, context) {
                return '已收到 ' + ((context && context.sourceLabel) || 'Agent') + ' 的返回结果，继续判断后续动作。';
            },
            final: withTask('现在各环节信息已齐，我给出“{task}”的最终调度结论。'),
            default: withTask('我继续观察全局，判断“{task}”接下来该调度谁。')
        },
        planner: {
            start: withTask('我先为“{task}”规划执行路线。'),
            done: withTask('规划完成，准备把路线建议回传给 Supervisor。'),
            promptNext: function (task, context) {
                return '按压一下，把规划结果回传给 ' + ((context && context.targetLabel) || 'Supervisor') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的规划结果：关于“' + task + '”，已形成执行路线。');
            }
        },
        researcher: {
            start: withTask('我先收集“{task}”需要的外部信息。'),
            done: withTask('信息收集完成，准备回传给 Supervisor。'),
            promptNext: function (task, context) {
                return '按压一下，把研究结果回传给 ' + ((context && context.targetLabel) || 'Supervisor') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的研究结果：关于“' + task + '”，外部信息已收集完成。');
            }
        },
        builder: {
            start: withTask('我先生成“{task}”的初版结果。'),
            done: withTask('初版生成完成，准备提交给 Supervisor。'),
            promptNext: function (task, context) {
                return '按压一下，把生成结果回传给 ' + ((context && context.targetLabel) || 'Supervisor') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的生成结果：关于“' + task + '”，初版内容已准备好。');
            }
        },
        reviewer: {
            start: withTask('我先审查“{task}”答案中的漏洞。'),
            done: withTask('审查完成，准备将问题与建议反馈给 Supervisor。'),
            promptNext: function (task, context) {
                return '按压一下，把审查建议回传给 ' + ((context && context.targetLabel) || 'Supervisor') + '。';
            },
            result: function (task, context) {
                return (context && context.result) || ('这是我的审查结果：关于“' + task + '”，风险点与改进建议已整理。');
            }
        }
    }
}
