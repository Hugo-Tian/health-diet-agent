"""Small, versioned lexical RAG. No external embedding service or patient index."""
import json,re
from urllib.parse import urlparse
from pathlib import Path
from datetime import date
from functools import lru_cache
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from .db import utcnow
from .retrieval import rank_chunks

CATALOG=Path(__file__).resolve().parents[1]/'data'/'health_guidance.json'

@lru_cache(maxsize=1)
def corpus():
    data=json.loads(CATALOG.read_text(encoding='utf-8'))
    ids=set()
    for row in data['chunks']:
        url=urlparse(row['url'])
        allowed=(url.hostname=='www.niddk.nih.gov' and url.path.startswith('/health-information/')) or (url.hostname=='www.nhlbi.nih.gov' and url.path.startswith('/health/'))
        if row['id'] in ids or url.scheme!='https' or url.username or url.port or not allowed:
            raise ValueError('Invalid knowledge source')
        for field in ('title','content','excerpt','limits','audience','section','source_reviewed','topic_key','publisher'):
            if not isinstance(row.get(field),str) or not row[field].strip():raise ValueError('Incomplete knowledge metadata: '+field)
        if not row.get('aliases') or not all(isinstance(a,str) and a.strip() for a in row['aliases']):raise ValueError('Invalid aliases')
        if date.fromisoformat(row['verified_on'])>date.fromisoformat(row['review_due']):raise ValueError('Invalid review dates')
        ids.add(row['id'])
    return data

def tokens(text):
    text=text.lower()
    return set(re.findall(r'[a-z]+',text))|{text[i:i+2] for i in range(len(text)-1) if all('\u4e00'<=x<='\u9fff' for x in text[i:i+2])}

class HealthGuidanceRetriever(BaseRetriever):
    """Two lexical rankings with topic diversity and per-chunk expiry."""
    def _get_relevant_documents(self,query,*,run_manager):
        data=corpus()
        if utcnow().date()>date.fromisoformat(data['review_due']):return []
        active=[r for r in data['chunks'] if utcnow().date()<=date.fromisoformat(r['review_due'])]
        return [Document(page_content=row['content'],metadata={**row,'version':data['version'],'scope':data['scope'],'retrieval':info})
                for row,info in rank_chunks(query,active)]

def search_guidance(query):
    docs=HealthGuidanceRetriever().invoke(query)
    sources=[{k:v for k,v in d.metadata.items() if k not in ('aliases','questions')} for d in docs]
    return {'status':'matched' if sources else 'no_match','version':corpus()['version'],
            'sources':sources,'notice':'仅检索已核对的成人饮食教育资料，未命中不表示不存在相关证据。检索结果不是诊断或治疗处方。'}

def contextual_guidance(query,previous_questions):
    """Only resolve explicit follow-up references from the nearest user question.

    Never index personal records or use a model's old answer as medical evidence.
    """
    result=search_guidance(query)
    if result['sources'] or not re.search(r'刚才|上述|这种情况|这个病|那我|那可以',query):return result
    if previous_questions:
        previous=search_guidance(previous_questions[-1])
        if previous['sources']:
            topics=list(dict.fromkeys(r['topic'] for r in previous['sources']))
            result=search_guidance(query+' '+' '.join(topics));result['context_resolved']=True
    return result

def urgent_response(message):
    # Narrow high-salience symptom check, not a complete triage classifier.
    for match in re.finditer(r'吐血|呕血|黑便|柏油(?:样)?便|持续剧烈腹痛',message):
        if re.search(r'(?:没有|无|未出现|否认|没有出现)[^，。！？；]{0,8}$',message[:match.start()]):continue
        source=next((r for r in search_guidance('消化性溃疡')['sources'] if r['id']=='ulcer-warning'),None)
        if source:return {'mode':'health_guidance','summary':'你提到的症状可能需要紧急医疗评估，请立即就医或联系当地急救服务，不要等待饮食计划。','suggestions':['聊天不能确定原因，本次不生成菜单。'],'citations':[source], 'knowledge_status':'matched','proposals':[],'batches':[],'tool_trace':['search_health_guidance:auto'],'requires_confirmation':False}
    return None
