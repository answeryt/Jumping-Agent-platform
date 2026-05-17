const fs = require('fs');
const path = require('path');
const WRONG = 'motion';
const RIGHT = 'div';

['AgentChatApp.js', 'index.js'].forEach((name) => {
    const p = path.join(__dirname, name);
    let s = fs.readFileSync(p, 'utf8');
    s = s.split(`'${WRONG}'`).join(`'${RIGHT}'`);
    s = s.split(`createElement('${WRONG}')`).join(`createElement('${RIGHT}')`);
    fs.writeFileSync(p, s);
    console.log('fixed', name);
});
