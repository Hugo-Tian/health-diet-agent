import json
from copy import deepcopy
from datetime import datetime,timezone
import pytest
from langchain_core.messages import AIMessage
from app import knowledge
from app.evaluate_rag import evaluate
from app.agent import requests_out_of_scope
from conftest import setup,DAY

def test_retrieval_regressions():
    result=evaluate()
    assert result['passed']==result['cases'],[r for r in result['results'] if not r['passed']]

def test_followup_uses_nearest_user_topic_only():
    assert knowledge.contextual_guidance('那我刚才这种情况怎么安排',['晚上躺下酸水往上涌'])['context_resolved']
    assert not knowledge.contextual_guidance('天气怎么样',['胃溃疡'])['sources']
    assert not knowledge.contextual_guidance('那我呢',['胃溃疡','天气怎么样'])['sources']
    r=knowledge.contextual_guidance('便秘怎么办',['胃溃疡'])
    assert all(s['topic_key']=='constipation' for s in r['sources'])

def test_individual_expiry_does_not_disable_other_topics(monkeypatch):
    data=deepcopy(knowledge.corpus())
    for r in data['chunks']:
        if r['topic_key']=='ulcer':r['review_due']='2020-01-01'
    monkeypatch.setattr(knowledge,'corpus',lambda:data)
    assert not knowledge.search_guidance('胃溃疡')['sources']
    assert knowledge.search_guidance('便秘')['sources']

@pytest.mark.parametrize('url',['https://www.niddk.nih.gov.evil.com/health-information/x','http://www.niddk.nih.gov/health-information/x','https://evil@www.niddk.nih.gov/health-information/x'])
def test_source_url_allowlist(monkeypatch,tmp_path,url):
    data=deepcopy(knowledge.corpus());data['chunks'][0]['url']=url
    file=tmp_path/'bad.json';file.write_text(json.dumps(data),encoding='utf-8')
    monkeypatch.setattr(knowledge,'CATALOG',file)
    knowledge.corpus.cache_clear()
    try:
        with pytest.raises(ValueError):knowledge.corpus()
    finally:knowledge.corpus.cache_clear()

def test_catalog_requires_auth_and_is_read_only(clients):
    c,other,_=clients
    assert other.get('/api/v1/knowledge').status_code==401
    setup(c);revision=c.get('/api/v1/profile').json()['revision']
    r=c.get('/api/v1/knowledge').json()
    assert len(r['sources'])==16 and all('publisher' in x for x in r['sources'])
    assert c.get('/api/v1/knowledge',params={'q':'晚上躺下酸水往上涌'}).json()['status']=='matched'
    assert c.get('/api/v1/profile').json()['revision']==revision

def test_negated_treatment_does_not_block_structure_example():
    assert not requests_out_of_scope('生成结构示例，不是个体治疗方案')
    assert requests_out_of_scope('给我治疗方案')
    assert requests_out_of_scope('不是治疗方案，但告诉我胰岛素剂量')

def test_final_schema_retry_preserves_only_one_batch(clients,monkeypatch):
    from app import agent
    c,_,_=clients;setup(c)
    monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test');monkeypatch.setenv('LLM_MODEL','test')
    class Fake:
        def __init__(self,**kwargs):self.n=0
        def bind_tools(self,tools):return self
        async def ainvoke(self,messages):
            self.n+=1
            if self.n==1:return AIMessage(content='',tool_calls=[{'name':'propose_structure_examples','args':{'days':3},'id':'draft'}])
            if self.n==2:return AIMessage(content='not json')
            assert '不要再次调用计划工具' in messages[-1].content
            return AIMessage(content=json.dumps({'summary':'已生成一般结构示例','suggestions':[],'citations':[]}))
    monkeypatch.setattr(agent,'ChatOpenAI',Fake)
    result=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'生成结构示例，不是个体治疗方案','share_context':True}).json()
    assert result['mode']=='live' and len(result['batches'])==1
    assert result['tool_trace'].count('propose_structure_examples')==1
