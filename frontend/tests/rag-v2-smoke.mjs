// Synthetic account only. Exercises production API and the built UI.
import {chromium} from '@playwright/test'
import fs from 'node:fs/promises'
const base=process.env.APP_TEST_URL||'http://127.0.0.1:8002'
const browser=await chromium.launch({headless:true})
const context=await browser.newContext({viewport:{width:1440,height:1000}})
const api=context.request,page=await context.newPage(),errors=[]
page.on('pageerror',e=>errors.push(e.message))
let headers,registered=false
async function get(p){const r=await api.get(base+'/api/v1'+p);if(!r.ok())throw new Error('GET '+r.status());return r.json()}
async function ask(message,date){
 const r=await api.post(base+'/api/v1/assistant/messages',{headers,data:{date,message,share_context:true},timeout:90000})
 if(!r.ok())throw new Error('Chat HTTP '+r.status())
 const a=await r.json();console.log(JSON.stringify({mode:a.mode,tools:a.tool_trace,citations:a.citations?.map(s=>s.id),error:a.error_code}))
 if(a.mode!=='live')throw new Error('Expected live: '+a.error_code)
 return a
}
try{
 const r=await api.post(base+'/api/v1/auth/register',{data:{email:`v2-${Date.now()}@example.com`,password:'synthetic-v2-only-12345'}})
 if(!r.ok())throw new Error('Register failed')
 headers={'X-CSRF-Token':(await r.json()).csrf};registered=true
 const p=await get('/profile');Object.assign(p.profile,{adult:true,age:25,goal_confirmed:true,special:['治疗性饮食']})
 const saved=await api.patch(base+'/api/v1/profile',{headers,data:{revision:p.revision,profile:p.profile}});if(!saved.ok())throw new Error('Profile failed')
 await page.goto(base+'/assistant')
 await page.getByText('浏览饮食知识库与检索示例',{exact:true}).click()
 await page.getByText(/16 个片段/).waitFor()
 await page.getByLabel('检索问题',{exact:true}).fill('晚上躺下酸水往上涌')
 await page.getByRole('button',{name:'检索资料',exact:true}).click()
 await page.getByText(/1 个片段/).waitFor()
 await page.locator('.knowledge-panel .guidance-sources summary').first().click()
 if(!(await page.getByRole('link',{name:'查看官方原文 ↗'}).first().getAttribute('href')).startsWith('https://www.niddk.nih.gov/'))throw new Error('Bad source')
 await fs.mkdir('../work/browser',{recursive:true})
 await page.screenshot({path:'../work/browser/rag-v2-desktop.png',fullPage:true})
 await page.setViewportSize({width:390,height:844})
 if(await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth))throw new Error('Mobile overflow')
 await page.screenshot({path:'../work/browser/rag-v2-mobile.png',fullPage:true})
 const a=await ask('晚上躺下酸水往上涌，饮食时间有什么参考？',p.today)
 if(!a.citations.some(s=>s.id==='reflux-timing'))throw new Error('Missing colloquial retrieval')
 const b=await ask('那我刚才这种情况，睡前进餐有什么依据？',p.today)
 if(!b.citations.some(s=>s.id==='reflux-timing'))throw new Error('Missing follow-up source')
 const c=await ask('请生成未来三天一般结构示例，不是个体治疗方案。',p.today)
 if(c.batches?.[0]?.proposals.length!==3)throw new Error('Missing structure cards')
 for(const prop of c.batches[0].proposals)if((await get('/plans?date='+prop.date)).active)throw new Error('Premature plan activation')
 await page.reload();await page.getByRole('button',{name:'确认未来 3 天计划',exact:true}).last().waitFor()
 if(errors.length)throw new Error(errors.join(';'))
 console.log('PASS: knowledge browser, desktop/mobile, real colloquial RAG, follow-up evidence, pending structure cards.')
}finally{
 if(registered){const p=await get('/profile');const d=await api.delete(base+`/api/v1/account?revision=${p.revision}&confirm=DELETE`,{headers});if(!d.ok())throw new Error('Account cleanup failed')}
 await browser.close()
}
