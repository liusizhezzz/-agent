const { profiles } = require('./prompt_compiler');

const signals = {
  fox: ['刷短视频','报复性','舍不得结束','属于我的时间','停不下来'],
  plant: ['仪式','放松','切换','兴奋','房间','洗澡'],
  soil: ['待办','明天','盘算','没做完','脑子','工作','担心'],
  light: ['睡不着','害怕躺下','盯着时间','越努力','失眠','焦虑入睡']
};

function matchAgent(text = '') {
  const value = String(text);
  const ranked = profiles.map(profile => ({
    profile,
    score: (signals[profile.id] || []).reduce((n, word) => n + (value.includes(word) ? 1 : 0), 0)
  })).sort((a, b) => b.score - a.score);
  const winner = ranked[0].profile;
  const reason = ranked[0].score
    ? `你提到“${(signals[winner.id] || []).find(word => value.includes(word))}”，今晚更适合从${winner.worldObject}开始。`
    : '今晚先从最稳的土壤开始；你仍可以随时切换。';
  return { agent: winner, reason, scores: ranked.map(x => ({ id: x.profile.id, score: x.score })) };
}

module.exports = { matchAgent };
