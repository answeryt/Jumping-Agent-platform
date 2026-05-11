'use strict'

var AudioManager = function () {
    this.instances = {};
    this.isOk = 0;
    this.unlocked = false;
    this.primed = false;
    this._resumePromise = null;
    this.audioConfig = [
        // 'bg',
        'cool',
        'perfect',
        'success',
        'fail',
        'start',
        'push',
        'push_loop',
    ];
    this.SoundJS = createjs.Sound;
    
    this._registerMusic();
    this._initMusicInstance();
}

Object.assign(AudioManager.prototype, {
    _registerMusic : function(){
        // console.log(createjs, this.SoundJS)
        this.SoundJS.alternateExtensions = ["mp3"];
        this.SoundJS.on("fileload", ()=>{
            this.isOk+=1;
            if(this.isOk == this.audioConfig.length) console.log("Loading Sound ... 100%");
        });
        for(let i=0;i<this.audioConfig.length;i++){
            let c = this.audioConfig[i];
            // this.SoundJS.registerSound(`../../res/audio/${c}.mp3`, c, i);
            this.SoundJS.registerSound(`./res/audio/${c}.mp3`, c, i);
        }
    },
    _initMusicInstance: function(){
        for(let i=0;i<this.audioConfig.length;i++){
            let c = this.audioConfig[i];
            this.instances[c] = null;
        }
    },
    unlock: function(prime){
        if (this.unlocked && (!prime || this.primed)) {
            return;
        }
        this.unlocked = true;
        var plugin = this.SoundJS.activePlugin;
        var context = plugin && plugin.context;
        if (context && context.state === 'suspended' && context.resume) {
            // 保存 Promise 供 play() 复用，避免在手势上下文之外重复调用 resume()
            this._resumePromise = context.resume();
            if (this._resumePromise && this._resumePromise.then) {
                this._resumePromise.then(function () {
                    this.unlocked = true;
                    this._resumePromise = null;
                }.bind(this)).catch(function () {
                    this.unlocked = false;
                    this._resumePromise = null;
                }.bind(this));
            }
            // 修复：不在此处同步覆盖 this.unlocked，因为 resume() 是异步的，
            // 此时 context.state 仍为 'suspended'，会错误地将 unlocked 重置为 false
        } else if (context) {
            this.unlocked = context.state === 'running';
        } else {
            this.unlocked = false;
        }
        if (createjs.WebAudioPlugin && createjs.WebAudioPlugin.playEmptySound) {
            createjs.WebAudioPlugin.playEmptySound();
        }
        if (prime && !this.primed) {
            var didPrime = false;
            this.audioConfig.forEach(function (key) {
                var ins = this.SoundJS.play(key, null, 0, 0, 0, 0);
                if (ins) {
                    didPrime = true;
                    ins.stop();
                }
            }.bind(this));
            this.primed = didPrime;
        }
    },
    play(key){
        if (this.audioConfig.indexOf(key) === -1) {
            return null;
        }
        this.unlock();
        var plugin = this.SoundJS.activePlugin;
        var context = plugin && plugin.context;
        if (context && context.state === 'suspended') {
            // AudioContext 尚未就绪（常见于移动端 setTimeout 回调中）
            // 复用手势处理器中已发起的 resume Promise，不重新调用 context.resume()
            var waitFor = this._resumePromise || context.resume();
            if (waitFor && waitFor.then) {
                waitFor.then(function () {
                    var ins = this.SoundJS.play(key);
                    if (ins) {
                        this.instances[key] = ins;
                        ins.volume = (key === 'bg') ? 0.2
                            : (key === 'cool' || key === 'perfect') ? 1 : 0.7;
                    }
                }.bind(this));
            }
            return null;
        }
        let ins = this.SoundJS.play(key);
        if (!ins) {
            return null;
        }
        this.instances[key] = ins;
        ins.volume = 0.7;
        if(key === 'bg') ins.volume = 0.2;
        else if(key === 'cool' || key === 'perfect') ins.volume = 1;
        return ins;
    },
    stop(key){
        let ins = this.instances[key];
        if (ins) {
            ins.stop();
        }
    },
    replay(key){
        this.stop(key);
        return this.play(key);
    }
})
module.exports = AudioManager
