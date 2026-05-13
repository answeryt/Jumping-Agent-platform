'use strict'

function withTask(text) {
    return function (task) {
        return text.replace(/\{task\}/g, task);
    }
}

module.exports = {
    withTask: withTask
}
