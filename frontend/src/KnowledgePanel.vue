<script setup lang="ts">
import { ref } from 'vue'
import { useSession } from './store'
import GuidanceSources from './GuidanceSources.vue'
const session=useSession(),query=ref(''),data=ref<any>(null),error=ref(''),busy=ref(false)
async function load(all=false){
  if(busy.value)return
  busy.value=true;error.value=''
  try{data.value=await session.api('/knowledge'+(!all&&query.value.trim()?'?q='+encodeURIComponent(query.value.trim()):''))}
  catch(e:any){error.value=e.message}finally{busy.value=false}
}
function toggle(e:Event){if((e.target as HTMLDetailsElement).open&&!data.value)load(true)}
</script>
<template>
  <details class="knowledge-panel" @toggle="toggle">
    <summary>浏览饮食知识库与检索示例</summary>
    <p>查看收录的资料和原文来源，或输入问题查看能检索到哪些内容。这里不会生成回答或修改计划。</p>
    <form @submit.prevent="load()"><label for="knowledge-query">检索问题</label><input id="knowledge-query" v-model="query" maxlength="1000" placeholder="例如：晚上躺下酸水往上涌"><div><button :disabled="busy">{{ busy?'正在读取…':'检索资料' }}</button><button type="button" :disabled="busy" @click="load(true)">查看全部</button></div></form>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="data">版本：{{ data.version }} · {{ data.sources.length }} 个片段</p>
    <p v-if="data&&!data.sources.length">当前知识库未检索到匹配资料；不代表医学上没有相关证据。</p>
    <GuidanceSources v-if="data" :sources="data.sources" title="知识库参考资料"/>
  </details>
</template>
<style scoped>
.knowledge-panel{margin:18px 0;padding:18px;background:#fff;border:1px solid #d5e2f2;border-radius:12px;overflow-wrap:anywhere}.knowledge-panel>summary{cursor:pointer;color:#2557a7;font-weight:600}.knowledge-panel p{line-height:1.8;font-size:13px}.knowledge-panel form{display:grid;gap:8px}.knowledge-panel input{width:100%;box-sizing:border-box}.knowledge-panel form div{display:flex;flex-wrap:wrap;gap:8px}
</style>
