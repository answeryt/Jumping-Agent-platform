'use strict'

const DEFAULT = {
    scale: {
        x: 0.4,
        y: 0.415,
        z: 0.415
    },
    rotation: {
        x: 0,
        y: 0,
        z: 0
    },
    position: {
        x: 0,
        y: 0,
        z: 0
    }
}

var ModelConfig = function(){}

ModelConfig.prototype = {
    objList:[
        'shoutixiang',
        'shudun',
        'x_hezi5',
        'q_hezi4',
        'd_hezi4',
        'd_hezi5',
        'pingtai1',
        'huaban',
        'dangao',
        'x_fangzhuo',
        'x_huaban',
        'x_yuanzhu1',
        'x_xigua',
        'q_shudun',
        'd_tiaotai',
        'd_xiaoniao',
        'd_pixiang',
        'd_yuanzhu1',
        'cheng',
        'cd'
    ],
    d_xiaoniao:{
        scale: DEFAULT.scale,
        rotation: {
            x: 0,
            y: -1/2,
            z: 0
        },
        position: {
            x: 0,
            y: 0,
            z: 0
        }
    },
    shoutixiang:{
        scale: DEFAULT.scale,
        rotation: {
            x: 0,
            y: -1/2,
            z: 0
        },
        position: {
            x: 0,
            y: 0,
            z: 0
        }
    },
    d_pixiang:{
        scale: DEFAULT.scale,
        rotation: {
            x: 0,
            y: -1/2,
            z: 0
        },
        position: {
            x: 0,
            y: 0,
            z: 0
        }
    },
    shudun:{
        scale: DEFAULT.scale,
        rotation: {
            x: 0,
            y: -1/2,
            z: 0
        },
        position: {
            x: 0,
            y: 0,
            z: 0
        }
    },
    x_hezi5:{
        scale: {
            x: 0.4,
            y: 0.415,
            z: 0.4
        },
        rotation: DEFAULT.rotation,
        position: DEFAULT.position
    },
    q_hezi4:{
        scale: {
            x: 0.4,
            y: 0.415,
            z: 0.4
        },
        rotation: DEFAULT.rotation,
        position: DEFAULT.position
    },
    d_hezi4:{
        scale: {
            x: 0.4,
            y: 0.415,
            z: 0.4
        },
        rotation: DEFAULT.rotation,
        position: DEFAULT.position
    },
    d_hezi5:{
        scale: {
            x: 0.4,
            y: 0.415,
            z: 0.4
        },
        rotation: DEFAULT.rotation,
        position: DEFAULT.position
    },
    pingtai1: DEFAULT,
    huaban: DEFAULT,
    dangao: DEFAULT,
    x_fangzhuo: DEFAULT,
    x_huaban: DEFAULT,
    x_yuanzhu1: DEFAULT,
    x_xigua: DEFAULT,
    q_shudun: DEFAULT,
    d_tiaotai: DEFAULT,
    d_yuanzhu1: DEFAULT,
    cheng: DEFAULT,
    cd: DEFAULT
}

module.exports = ModelConfig