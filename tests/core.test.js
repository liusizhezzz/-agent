const assert = require('node:assert/strict');
const { profiles, compilePrompt } = require('../prompt_compiler');
const { matchAgent } = require('../agent_matcher');

const required = ['id','worldObject','name','personality','cbtiFocus','适用场景','speechStyle','openingLines','followUpRules','silencePolicy','farewellRules','voice','backgroundSound'];
assert.equal(profiles.length, 4);
assert.equal(new Set(profiles.map(p => p.id)).size, 4);
for (const p of profiles) for (const key of required) assert.ok(p[key], `${p.id}.${key}`);
const prompt = compilePrompt('soil', { userText: '明天还有很多待办' });
for (const needle of ['沉砚','脚下的土壤','担忧卸载','Final ASR','RAG','不诊断']) assert.match(prompt, new RegExp(needle));
assert.equal(matchAgent('我脑子里一直盘算明天没做完的待办').agent.id, 'soil');
assert.equal(matchAgent('越努力越睡不着，害怕躺下').agent.id, 'light');
assert.equal(matchAgent('想刷短视频补偿一下').agent.id, 'fox');
assert.equal(matchAgent('我想建立睡前仪式，先放松').agent.id, 'plant');
console.log('core checks passed');
