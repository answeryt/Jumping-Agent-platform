'use strict'

function withTask(text) {
    return function (task) {
        return text.replace(/\{task\}/g, task);
    }
}

var FlowTemplates = [
    {
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
            a: 'what next',
            b: withTask('我先围绕“{task}”收集线索。'),
            c: withTask('我把“{task}”拆成趋势、证据和结论。'),
            d: withTask('我给出“{task}”的最终答案。')
        }
    },
    {
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
            dispatcher: 'what next',
            tech: withTask('“{task}”更像技术趋势问题，先走技术分支。'),
            finance: withTask('我补充“{task}”背后的增长和采用价值。'),
            legal: withTask('我检查“{task}”可能带来的风险和限制。'),
            result: withTask('我把各分支对“{task}”的判断合成答案。')
        }
    },
    {
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
            dispatcher: 'what next',
            w1: withTask('我负责找“{task}”的数据证据。'),
            w2: withTask('我负责判断“{task}”里的技术方向。'),
            w3: withTask('我负责观察“{task}”的社区讨论。'),
            aggregator: withTask('我把并行结果合成“{task}”的完整结论。')
        }
    },
    {
        id: 'loop',
        name: '循环反思',
        description: '执行者产出结果，评估者反馈，不通过则回到执行者。',
        visualMode: 'linear_jump',
        nodes: [
            { id: 'executor', role: 'executor', x: -5, z: 0, label: '执行 Agent' },
            { id: 'evaluator', role: 'evaluator', x: 5, z: 0, label: '评估 Agent' },
            { id: 'approved', role: 'agent', x: 5, z: -9, label: '通过' }
        ],
        jumpSequence: ['executor', 'evaluator', 'executor', 'evaluator', 'approved'],
        dialogues: {
            executor: 'what next',
            evaluator: withTask('我检查“{task}”的答案是否可信。'),
            approved: withTask('质量通过，可以输出“{task}”的答案。')
        }
    },
    {
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
            optimist: withTask('我先从机会角度看“{task}”：哪些趋势值得下注？'),
            pessimist: withTask('我质疑“{task}”：热度是否只是短期噪声？'),
            realist: withTask('我折中判断“{task}”：看数据、生态和落地场景。'),
            moderator: withTask('我总结辩论，形成“{task}”的共识。')
        }
    },
    {
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
            manager: 'what next',
            dev: withTask('我负责研究“{task}”的核心资料。'),
            tester: withTask('我验证“{task}”的证据是否可靠。'),
            designer: withTask('我把“{task}”整理成小白能懂的表达。'),
            final: withTask('我汇总团队对“{task}”的成果。')
        }
    },
    {
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
            supervisor: 'what next',
            planner: withTask('我为“{task}”制定执行路线。'),
            researcher: withTask('我收集“{task}”需要的外部信息。'),
            builder: withTask('我生成“{task}”的初版结果。'),
            reviewer: withTask('我审查“{task}”答案的漏洞。')
        }
    }
]

module.exports = FlowTemplates
