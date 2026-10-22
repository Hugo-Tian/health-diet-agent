// Real provider smoke: synthetic account only; creates and deletes its own data.
import {chromium} from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'
const base=process.env.APP_TEST_URL||'http://127.0.0.1:8000',out=path.resolve('../work/browser')
await fs.mkdir(out,{recursive:true})
const browser=await chromium.launch({headless:true}),context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[]
page.on('pageerror',e=>errors.push(e.message))
const api=context.request
const registered=await api.post(base+'/api/v1/auth/register',{data:{email:`rag-${Date.now()}@example.com`,password:'synthetic-rag-test-12345'}})
if(!registered.ok())throw new Error('Registration failed')
const {csrf}=await registered.json(),headers={'X-CSRF-Token':csrf}
async function get(p){return (await api.get(base+'/api/v1'+p)).json()}
async function ask(message,day){
 const r=await api.post(base+'/api/v1/assistant/messages',{headers,data:{date:day,message,share_context:true},timeout:90000})
 if(!r.ok())throw new Error('Chat HTTP '+r.status())
 const result=await r.json()
 console.log(JSON.stringify({mode:result.mode,tools:result.tool_trace,citations:result.citations?.map(c=>c.id),error:result.error_code}))
 if(result.mode!=='live')throw new Error('Not live: '+result.mode)
 return result
}
try{
 const p=await get('/profile');p.profile.adult=true;p.profile.age=25;p.profile.goal_confirmed=true
 const saved=await api.patch(base+'/api/v1/profile',{headers,data:{revision:p.revision,profile:p.profile}});if(!saved.ok())throw new Error('Profile failed')
 const first=await ask('我有胃溃疡，帮我生成未来三天的计划。先说明有依据的饮食原则。',p.today)
 if(!first.citations.some(c=>c.id==='ulcer-diet'))throw new Error('Missing ulcer source')
 if(first.citations.some(c=>c.id.startsWith('reflux')))throw new Error('Unrelated reflux source')
 await page.goto(base+'/assistant')
 await page.getByRole('heading',{name:'本次引用的参考资料'}).first().waitFor()
 await page.locator('.guidance-sources summary').first().click()
 const link=page.getByRole('link',{name:'查看官方原文 ↗'}).first()
 await link.waitFor()
 if(!(await link.getAttribute('href')).startsWith('https://www.niddk.nih.gov/'))throw new Error('Unexpected citation URL')
 await page.screenshot({path:path.join(out,'rag-desktop.png'),fullPage:true})
 await page.setViewportSize({width:390,height:844})
 if(await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth))throw new Error('Mobile overflow')
 await page.screenshot({path:path.join(out,'rag-mobile.png'),fullPage:true})
 const next=await ask('请基于刚才胃溃疡的参考资料，建立未来三天一般均衡饮食示例。我没有额外饮食限制或食物不耐受，不把它作为治疗方案，请生成待确认卡片。',p.today)
 if(!next.batches?.length)throw new Error('No general meal draft')
 if(!next.citations.length)throw new Error('No evidence with draft')
 const batch=next.batches[0]
 for(const prop of batch.proposals)if((await get('/plans?date='+prop.date)).active)throw new Error('Draft applied without confirmation')
 await page.reload();await page.getByRole('button',{name:'确认未来 3 天计划',exact:true}).last().waitFor()
 if(errors.length)throw new Error(errors.join(';'))
 await fs.writeFile(path.join(out,'rag-result.json'),JSON.stringify({passed:true,first_summary:first.summary,first_suggestions:first.suggestions,citations:first.citations.map(c=>c.id),draft_days:batch.proposals.length,desktop:1440,mobile:390},null,2))
 console.log('PASS: real RAG answer, source UI, mobile, follow-up structured plan remains pending.')
}catch(e){await page.screenshot({path:path.join(out,'rag-failure.png'),fullPage:true});throw e}
finally{const p=await get('/profile');const r=await api.delete(base+`/api/v1/account?revision=${p.revision}&confirm=DELETE`,{headers});if(!r.ok())console.error('Cleanup failed');await browser.close()}
