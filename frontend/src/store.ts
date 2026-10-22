import { defineStore } from 'pinia'
import { ref } from 'vue'
export const useSession = defineStore('session', () => {
  const csrf = ref(''), email = ref(''), revision = ref(0), loggedIn = ref(false)
  async function api(path:string, method='GET', body?:unknown):Promise<any> {
    let response:Response
    try {response = await fetch('/api/v1'+path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf.value},body:body===undefined?undefined:JSON.stringify(body)})}
    catch {throw new Error('无法连接服务器。此次操作未确认保存，请恢复连接后刷新核对。')}
    if(!response.ok){
      if(response.status===401) loggedIn.value=false
      const error=await response.json().catch(()=>({}))
      throw new Error(error.detail?.message || `操作失败（${response.status}），请重试`)
    }
    return response.json()
  }
  async function restore(){
    const me=await api('/auth/me');csrf.value=me.csrf;email.value=me.email;revision.value=me.revision;loggedIn.value=true
  }
  return {csrf,email,revision,loggedIn,api,restore}
})
