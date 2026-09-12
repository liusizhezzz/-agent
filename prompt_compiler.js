const fs = require('node:fs');
const path = require('node:path');
const profiles = JSON.parse(fs.readFileSync(path.join(__dirname, 'agent_profiles.json'), 'utf8'));
const BASE_SAFETY = `你服务于睡前陪伴场景，但首先要像一个真实、自然的聊天对象，允许用户自由谈论任何事情。不要把每句话都套进星球或物件的比喻，不使用固定的鸡汤式开场，不为了体现专业而强行提问或给建议。先回应用户刚刚说的内容，再判断是否需要建议；用户只想聊天时就跟着聊。每次回复通常1至3句，最多一个自然问题，使用口语、具体、不过度修饰的表达。先共情理解，再给建议；不规训、不诊断、不承诺治疗或立即入睡，不制造依赖。用户回答变短、烦躁或说不想聊时减少提问，改为短句和可跳过选项。静默3至5秒先判断是在思考还是想结束；明确困倦、拒绝或结束时礼貌告别。只在Final ASR完成后触发RAG和正式回复；RAG超时使用基础角色Prompt，迟到结果不得补发第二条回复。`;
function getAgent(id){return profiles.find(p=>p.id===id)||profiles[0]}
function compilePrompt(agentId, ctx={}){const p=getAgent(agentId);return [BASE_SAFETY,`你的身份是${p.name}，世界物件是“${p.worldObject}”。`, `人格：${p.personality}`, `CBT-I侧重点：${p.cbtiFocus.join('、')}`, `适用场景：${p.适用场景.join('、')}`, `说话方式：${p.speechStyle}`, `跟进规则：${p.followUpRules.join('；')}`, `静默规则：${p.silencePolicy}`, `告别规则：${p.farewellRules}`, `代表性话术：${p.representativeLine}`, ctx.rag?`本轮RAG上下文（仅作参考）：${ctx.rag}`:'本轮暂无RAG上下文。', ctx.userText?`用户当前表达：${ctx.userText}`:''].filter(Boolean).join('\n')}
module.exports={profiles,getAgent,compilePrompt,BASE_SAFETY};
