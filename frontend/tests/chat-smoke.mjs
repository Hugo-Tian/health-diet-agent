import {chromium} from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'
const base=process.env.APP_TEST_URL||'http://127.0.0.1:8001',out=path.resolve('../work/browser')
await fs.mkdir(out,{recursive:true})
const browser=await chromium.launch({headless:true}),context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[]
page.on('pageerror',e=>errors.push(e.message))
const api=context.request
const reg=await api.post(base+'/api/v1/auth/register',{data:{email:`chat-ui-${Date.now()}@example.com`,password:'test-password-12345'}})
if(!reg.ok())throw new Error('Registration failed')
const {csrf}=await reg.json(),headers={'X-CSRF-Token':csrf}
async function get(p){return (await api.get(base+'/api/v1'+p)).json()}
async function noOverflow(label){if(await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth))throw new Error(label+' overflow')}
try{
 const profile=await get('/profile');profile.profile.adult=true;profile.profile.age=25;profile.profile.goal_confirmed=true
 const r=await api.patch(base+'/api/v1/profile',{headers,data:{revision:profile.revision,profile:profile.profile}});if(!r.ok())throw new Error('Profile failed')
 await page.goto(base+'/assistant')
 await page.getByRole('button',{name:'安排未来三天',exact:true}).click()
 await page.getByRole('button',{name:'发送',exact:true}).click()
 await page.getByRole('button',{name:'确认未来 3 天计划',exact:true}).waitFor()
 const before=await get('/assistant/history');const batch=before[0].answer.batches[0]
 for(const p of batch.proposals){if((await get('/plans?date='+p.date)).active)throw new Error('Draft applied without confirmation')}
 await noOverflow('desktop chat')
 await page.screenshot({path:path.join(out,'chat-desktop.png'),fullPage:true})
 await page.getByRole('button',{name:'确认未来 3 天计划',exact:true}).click()
 await page.getByText('整组已生效',{exact:true}).waitFor()
 for(const p of batch.proposals){if(!(await get('/plans?date='+p.date)).active)throw new Error('Missing confirmed day')}
 await page.reload();await page.getByText('整组已生效',{exact:true}).waitFor()
 await page.setViewportSize({width:390,height:844});await noOverflow('mobile chat');await page.screenshot({path:path.join(out,'chat-mobile.png'),fullPage:true})
 const pixel=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAIAAABvFaqvAAAAK0lEQVR4nGP8//8/AzUAE1VMYRg1iBgwahBhMGoQYTBqEGEwahBhMPgMAgAZ0QMtfEqnkAAAAABJRU5ErkJggg==','base64')
 await page.locator('input[type=file]').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:pixel})
 await page.getByAltText('本次准备识别的餐食照片').waitFor()
 await page.locator('.chat-composer input[type=checkbox]').check()
 await page.getByRole('button',{name:'识别并保存待确认记录',exact:true}).click()
 await page.getByRole('button',{name:'核对并确认记录',exact:true}).waitFor()
 const pending=await get('/daily-summary?date='+profile.today)
 if(pending.pending_count!==1||pending.actual.known.kcal!==0)throw new Error('Photo prematurely counted')
 await noOverflow('mobile photo');await page.screenshot({path:path.join(out,'chat-photo-mobile.png'),fullPage:true})
 await page.getByRole('button',{name:'核对并确认记录',exact:true}).click()
 await page.getByRole('dialog').waitFor()
 await page.getByLabel('是否吃完').selectOption('yes')
 await page.getByLabel('确认状态').selectOption('confirmed')
 await page.getByRole('button',{name:'保存实际记录',exact:true}).click()
 await page.getByRole('dialog').waitFor({state:'hidden'})
 await page.getByRole('button',{name:'查看 / 修改记录',exact:true}).waitFor()
 const final=await get('/daily-summary?date='+profile.today)
 if(final.confirmed_count!==1||final.actual.known.kcal!==195||final.actual.missing.kcal!==1)throw new Error('Confirmed nutrient sum mismatch')
 if(errors.length)throw new Error(errors.join(';'))
 console.log('PASS: 3-day preview/confirm/persist; photo upload/pending/review/confirmed; desktop/mobile no overflow. Vision uses isolated synthetic fixture.')
 await fs.writeFile(path.join(out,'chat-result.json'),JSON.stringify({passed:true,vision:'synthetic fixture',checks:['draft unchanged until confirmed','3-day atomic confirmation','history survives reload','photo upload','pending excluded','review and confirm','known195kcal and unknown retained','1440/390 no overflow','no browser exceptions']},null,2))
}catch(e){await page.screenshot({path:path.join(out,'chat-failure.png'),fullPage:true});throw e}
finally{const p=await get('/profile');const r=await api.delete(base+`/api/v1/account?revision=${p.revision}&confirm=DELETE`,{headers});if(!r.ok())console.error('Test account cleanup failed');await browser.close()}
