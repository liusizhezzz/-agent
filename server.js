const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { DatabaseSync } = require('node:sqlite');
const { profiles, getAgent, compilePrompt } = require('./prompt_compiler');
const { matchAgent } = require('./agent_matcher');

const ROOT = __dirname;
const PORT = Number(process.env.PORT || 4173);
const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY || '';
const ANTHROPIC_BASE_URL = (process.env.ANTHROPIC_BASE_URL || 'https://api.anthropic.com').replace(/\/$/, '');
const AGENT_MODEL = process.env.SLEEP_LANDING_AGENT_MODEL || 'claude-3-5-haiku-20241022';
const DATA_DIR = path.join(ROOT, 'data');
fs.mkdirSync(DATA_DIR, { recursive: true });
const db = new DatabaseSync(path.join(DATA_DIR, 'sleep-landing.sqlite'));
db.exec(`
  PRAGMA journal_mode = WAL;
  CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    wake_time TEXT NOT NULL DEFAULT '07:30',
    target_sleep TEXT NOT NULL DEFAULT '23:50',
    barrier TEXT NOT NULL DEFAULT '停不下来',
    preference TEXT NOT NULL DEFAULT '纯音频',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS landings (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    landing_date TEXT NOT NULL,
    target_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    current_step INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
  );
  CREATE TABLE IF NOT EXISTS morning_feedback (
    id TEXT PRIMARY KEY,
    landing_id TEXT NOT NULL,
    score INTEGER NOT NULL,
    difficulty TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(landing_id) REFERENCES landings(id)
  );
  CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
  );
  CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, agent_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created', background_sound TEXT NOT NULL DEFAULT 'space',
    prompt_version TEXT NOT NULL, created_at TEXT NOT NULL, ended_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
  );
  CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, user_id TEXT NOT NULL, agent_id TEXT NOT NULL,
    title TEXT NOT NULL, source_text TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
    object_name TEXT NOT NULL, object_icon TEXT NOT NULL, object_tone TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '日常事件', retention TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id), FOREIGN KEY(user_id) REFERENCES users(id)
  );
`);

const now = () => new Date().toISOString();
const dateKey = () => new Date().toISOString().slice(0, 10);
const demoUserId = 'demo-user';
const userExists = db.prepare('SELECT id FROM users WHERE id = ?').get(demoUserId);
if (!userExists) {
  const t = now();
  db.prepare('INSERT INTO users (id, created_at, updated_at) VALUES (?, ?, ?)').run(demoUserId, t, t);
}

function json(res, status, data) {
  const body = JSON.stringify(data);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*' });
  res.end(body);
}
function readBody(req) { return new Promise((resolve, reject) => { let raw=''; req.on('data', c => raw += c); req.on('end', () => { try { resolve(raw ? JSON.parse(raw) : {}); } catch { reject(new Error('invalid_json')); } }); }); }
function getUser() { return db.prepare('SELECT * FROM users WHERE id = ?').get(demoUserId); }
function getOrCreateLanding() {
  const user = getUser();
  let landing = db.prepare('SELECT * FROM landings WHERE user_id = ? AND landing_date = ? ORDER BY rowid DESC LIMIT 1').get(demoUserId, dateKey());
  if (!landing) {
    landing = { id: crypto.randomUUID(), user_id: demoUserId, landing_date: dateKey(), target_time: user.target_sleep, status: 'planned', current_step: 0, note: '', started_at: null, completed_at: null };
    db.prepare('INSERT INTO landings (id,user_id,landing_date,target_time,status,current_step,note) VALUES (?,?,?,?,?,?,?)').run(landing.id, landing.user_id, landing.landing_date, landing.target_time, landing.status, landing.current_step, landing.note);
  }
  return landing;
}
function dashboard() {
  const user = getUser();
  const landing = getOrCreateLanding();
  const feedback = db.prepare('SELECT score, difficulty, created_at FROM morning_feedback mf JOIN landings l ON l.id = mf.landing_id WHERE l.user_id = ? ORDER BY mf.created_at DESC LIMIT 7').all(demoUserId);
  const completed = db.prepare("SELECT COUNT(*) AS n FROM landings WHERE user_id = ? AND status = 'completed'").get(demoUserId).n;
  return { user, landing, feedback, metrics: { completed, reclaimedMinutes: completed * 27, healthyExitRate: completed ? 75 : 0 } };
}

function listMemories() { return db.prepare('SELECT * FROM memories WHERE user_id=? ORDER BY created_at DESC').all(demoUserId); }
function createSession(payload) { const agent=getAgent(String(payload.agent_id||'soil')); const id=crypto.randomUUID(); const t=now(); const background=['wind','space','rain','none'].includes(payload.background_sound)?payload.background_sound:agent.backgroundSound; db.prepare('INSERT INTO sessions (id,user_id,agent_id,status,background_sound,prompt_version,created_at) VALUES (?,?,?,?,?,?,?)').run(id,demoUserId,agent.id,'created',background,'agent-profile-v1',t); return {id,agent,status:'created',background_sound:background,prompt:compilePrompt(agent.id,{userText:String(payload.user_text||'')})}; }
function createMemory(sessionId,payload) { const session=db.prepare('SELECT * FROM sessions WHERE id=? AND user_id=?').get(sessionId,demoUserId); if(!session) return null; const agent=getAgent(session.agent_id); const obj=agent.memoryObject; const t=now(); const id=crypto.randomUUID(); const title=String(payload.title||obj.name).slice(0,120); const source=String(payload.source_text||'').slice(0,2000); db.prepare('INSERT INTO memories (id,session_id,user_id,agent_id,title,source_text,summary,object_name,object_icon,object_tone,category,retention,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)').run(id,sessionId,demoUserId,agent.id,title,source,String(payload.summary||agent.representativeLine).slice(0,500),obj.name,obj.icon,obj.tone,String(payload.category||'日常事件').slice(0,20),'pending',t,t); return db.prepare('SELECT * FROM memories WHERE id=?').get(id); }

function updateUser(payload) {
  const user = getUser();
  const wake = /^\d{2}:\d{2}$/.test(payload.wake_time || '') ? payload.wake_time : user.wake_time;
  const target = /^\d{2}:\d{2}$/.test(payload.target_sleep || '') ? payload.target_sleep : user.target_sleep;
  const barrier = String(payload.barrier || user.barrier).slice(0, 30);
  const preference = String(payload.preference || user.preference).slice(0, 30);
  db.prepare('UPDATE users SET wake_time=?, target_sleep=?, barrier=?, preference=?, updated_at=? WHERE id=?').run(wake, target, barrier, preference, now(), demoUserId);
  const landing = db.prepare('SELECT id FROM landings WHERE user_id=? AND landing_date=?').get(demoUserId, dateKey());
  if (landing) db.prepare("UPDATE landings SET target_time=? WHERE id=? AND status='planned'").run(target, landing.id);
  return dashboard();
}
async function commercialAgentReply({ text, screen, step }) {
  if (!ANTHROPIC_API_KEY) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(`${ANTHROPIC_BASE_URL}/v1/messages`, {
      method: 'POST',
      signal: controller.signal,
      headers: { 'content-type': 'application/json', 'x-api-key': ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: AGENT_MODEL,
        max_tokens: 100,
        temperature: 0.45,
        system: '你是眠眠兔，服务于青少年和年轻人的睡前行为支持产品。只给一句到两句短中文回复，语气温柔、具体、可跳过，不做诊断、不承诺治疗、不制造依赖、不评价用户。优先引导一个当下可完成的小动作。',
        messages: [{ role: 'user', content: `页面=${screen || 'unknown'}，步骤=${Number(step || 0)}。用户说：${text}` }]
      })
    });
    if (!response.ok) return null;
    const data = await response.json();
    const reply = data?.content?.find(item => item.type === 'text')?.text?.trim();
    return reply ? reply.slice(0, 240) : null;
  } catch (_) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
async function handleApi(req, res, pathname) {
  if (req.method === 'GET' && pathname === '/api/health') return json(res, 200, { ok: true, service: 'sleep-landing-api', time: now() });
  if (req.method === 'GET' && pathname === '/api/dashboard') return json(res, 200, dashboard());
  if (req.method === 'GET' && pathname === '/api/agents') return json(res, 200, { agents: profiles });
  if (req.method === 'POST' && pathname === '/api/agents/recommend') return json(res, 200, matchAgent((await readBody(req)).text || ''));
  if (req.method === 'GET' && pathname === '/api/memories') return json(res, 200, { memories: listMemories() });
  if (req.method === 'POST' && pathname === '/api/sessions') return json(res, 201, createSession(await readBody(req)));
  const sessionMatch = pathname.match(/^\/api\/sessions\/([^/]+)(?:\/end)?$/);
  if (sessionMatch && req.method === 'POST') { const id=sessionMatch[1]; const body=await readBody(req); const session=db.prepare('SELECT * FROM sessions WHERE id=? AND user_id=?').get(id,demoUserId); if(!session) return json(res,404,{error:'session_not_found'}); db.prepare('UPDATE sessions SET status=?,ended_at=? WHERE id=?').run('ended',now(),id); const memory=createMemory(id,body); if(memory && ['object','stone','discard'].includes(body.retention)) db.prepare('UPDATE memories SET retention=?,updated_at=? WHERE id=?').run(body.retention,now(),memory.id); return json(res,200,{session_id:id,status:'ended',memory,summary_provider:process.env.DASHSCOPE_API_KEY?'qwen-max':'pending_qwen_max'}); }
  const sessionMemoryMatch = pathname.match(/^\/api\/sessions\/([^/]+)\/memory$/);
  if (sessionMemoryMatch && req.method === 'GET') { const rows = db.prepare('SELECT * FROM memories WHERE session_id=? AND user_id=? ORDER BY created_at DESC').all(sessionMemoryMatch[1], demoUserId); return json(res,200,{memories:rows}); }
  const memoryMatch = pathname.match(/^\/api\/memories\/([^/]+)(?:\/retention)?$/);
  if (memoryMatch && req.method === 'GET') { const memory=db.prepare('SELECT * FROM memories WHERE id=? AND user_id=?').get(memoryMatch[1],demoUserId); return memory?json(res,200,{memory}):json(res,404,{error:'memory_not_found'}); }
  if (memoryMatch && req.method === 'PATCH') { const body=await readBody(req); const retention=['object','stone','discard','pending'].includes(body.retention)?body.retention:'pending'; const memory=db.prepare('SELECT id FROM memories WHERE id=? AND user_id=?').get(memoryMatch[1],demoUserId); if(!memory) return json(res,404,{error:'memory_not_found'}); db.prepare('UPDATE memories SET retention=?,updated_at=? WHERE id=?').run(retention,now(),memoryMatch[1]); return json(res,200,{memory:db.prepare('SELECT * FROM memories WHERE id=?').get(memoryMatch[1])}); }

  if (req.method === 'POST' && pathname === '/api/onboarding') return json(res, 200, updateUser(await readBody(req)));
  const landingMatch = pathname.match(/^\/api\/landings\/([^/]+)$/);
  if (landingMatch && req.method === 'PATCH') {
    const id = landingMatch[1]; const body = await readBody(req); const landing = db.prepare('SELECT * FROM landings WHERE id=? AND user_id=?').get(id, demoUserId);
    if (!landing) return json(res, 404, { error: 'landing_not_found' });
    const step = Math.max(0, Math.min(4, Number(body.current_step ?? landing.current_step)));
    const status = body.status === 'completed' ? 'completed' : step > 0 ? 'in_progress' : landing.status;
    const started = status !== 'planned' && !landing.started_at ? now() : landing.started_at;
    const completed = status === 'completed' ? now() : landing.completed_at;
    db.prepare('UPDATE landings SET current_step=?, status=?, note=?, started_at=?, completed_at=? WHERE id=?').run(step, status, String(body.note ?? landing.note).slice(0, 180), started, completed, id);
    return json(res, 200, dashboard());
  }
  if (req.method === 'POST' && pathname === '/api/morning-feedback') {
    const body = await readBody(req); const landing = getOrCreateLanding(); const score = Math.max(1, Math.min(5, Number(body.score || 3))); const difficulty = String(body.difficulty || '一般').slice(0, 10);
    db.prepare('INSERT INTO morning_feedback (id,landing_id,score,difficulty,created_at) VALUES (?,?,?,?,?)').run(crypto.randomUUID(), landing.id, score, difficulty, now());
    return json(res, 200, dashboard());
  }
  if (req.method === 'POST' && pathname === '/api/events') {
    const body = await readBody(req);
    const eventType = String(body.event_type || 'unknown').slice(0, 60);
    const payload = JSON.stringify(body.payload || {}).slice(0, 2000);
    db.prepare('INSERT INTO events (id,user_id,event_type,payload_json,created_at) VALUES (?,?,?,?,?)').run(crypto.randomUUID(), demoUserId, eventType, payload, now());
    return json(res, 201, { ok: true, event_type: eventType });
  }
  if (req.method === 'POST' && pathname === '/api/agent-message') {
    const body = await readBody(req);
    const text = String(body.text || '').slice(0, 240);
    db.prepare('INSERT INTO events (id,user_id,event_type,payload_json,created_at) VALUES (?,?,?,?,?)').run(crypto.randomUUID(), demoUserId, 'agent_message', JSON.stringify({ text }).slice(0, 2000), now());
    let reply = '先不用解决全部事情，我们只做眼前这一小步。';
    if (/焦虑|担心|脑子|想法/.test(text)) reply = '听见了。把这件事先放到明天清单，今晚让大脑休息一下。';
    if (/睡不着|失眠/.test(text)) reply = '今晚不追求立刻睡着，我们先离开屏幕，给身体一个安静的信号。';
    if (/不想|不行|失败/.test(text)) reply = '可以暂停，也可以只完成一步。眠眠不会因为你跳过而扣分。';
    const liveReply = await commercialAgentReply({ text, screen: body.screen, step: body.step });
    return json(res, 200, { reply: liveReply || reply, mode: 'supportive', provider: liveReply ? 'anthropic' : 'fallback', persisted: true });
  }
  return json(res, 404, { error: 'not_found' });
}
function serveStatic(req, res, pathname) {
  let filePath = pathname === '/' ? path.join(ROOT, 'index.html') : path.join(ROOT, pathname.replace(/^\//, ''));
  if (!filePath.startsWith(ROOT)) return json(res, 403, { error: 'forbidden' });
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) filePath = path.join(ROOT, 'index.html');
  const ext = path.extname(filePath); const types = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.png':'image/png', '.jpg':'image/jpeg', '.svg':'image/svg+xml' };
  res.writeHead(200, { 'Content-Type': types[ext] || 'application/octet-stream' }); fs.createReadStream(filePath).pipe(res);
}
const server = http.createServer(async (req, res) => { try { const url = new URL(req.url, `http://${req.headers.host}`); if (url.pathname.startsWith('/api/')) await handleApi(req, res, url.pathname); else serveStatic(req, res, url.pathname); } catch (error) { console.error(error); json(res, 400, { error: error.message || 'bad_request' }); } });
server.listen(PORT, () => console.log(`Sleep Landing running at http://localhost:${PORT}`));
