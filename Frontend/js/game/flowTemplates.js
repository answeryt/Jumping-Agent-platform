'use strict'

module.exports = [
    require('./workflows/flowTemplateSequential'),
    require('./workflows/flowTemplateRouter'),
    require('./workflows/flowTemplateParallel'),
    require('./workflows/flowTemplateLoop'),
    require('./workflows/flowTemplateDebate'),
    require('./workflows/flowTemplateHierarchical'),
    require('./workflows/flowTemplateSupervisor')
]
