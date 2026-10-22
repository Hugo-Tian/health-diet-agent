import json
from datetime import datetime,timezone
import pytest
from langchain_core.messages import AIMessage
from app.knowledge import search_guidance,corpus,urgent_response
from conftest import setup,DAY

@pytest.mark.parametrize('query,expected',[
    ('胃溃疡需要忌口吗','ulcer-diet'),('晚上反酸怎么办','reflux-timing'),
    ('便秘怎么吃','constipation-fiber'),('喝牛奶拉肚子','lactose-tolerance'),
])
def test_retrieval_is_topic_specific(query,expected):
    result=search_guidance(query)
    ids={r['id'] for r in result['sources']}
    assert expected in ids
    if expected=='ulcer-diet':assert not any(i.startswith('reflux') for i in ids)

@pytest.mark.parametrize('query',['口腔溃疡','糖尿病治疗','天气怎么样',''])
def test_unknown_topics_do_not_fill_with_unrelated_sources(query):
    assert search_guidance(query)['sources']==[]

def test_expired_corpus_is_not_used(monkeypatch):
    import app.knowledge as knowledge
    monkeypatch.setattr(knowledge,'utcnow',lambda:datetime(2028,1,1,tzinfo=timezone.utc))
    assert search_guidance('胃溃疡')['status']=='no_match'

def test_source_metadata_and_warning_negation():
    data=corpus();assert len(data['chunks'])>=16
    assert all(r['excerpt'] and r['source_reviewed'] and r['limits'] for r in data['chunks'])
    assert urgent_response('我有胃溃疡，没有黑便，也没有吐血') is None
    result=urgent_response('今天吐血，给我安排三餐')
    assert result['requires_confirmation'] is False and not result['proposals']
    assert result['citations'][0]['id']=='ulcer-warning'

def configure(monkeypatch):
    monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setenv('LLM_MODEL','test')

def test_real_tool_retrieval_and_citations_persist(clients,monkeypatch):
    import app.agent as agent
    c,b,_=clients;setup(c);configure(monkeypatch)
    class Fake:
        def __init__(self,**kw):self.n=0
        def bind_tools(self,tools):
            assert any(t.name=='search_health_guidance' for t in tools)
            return self
        async def ainvoke(self,messages):
            self.n+=1
            if self.n==1:return AIMessage(content='',tool_calls=[{'name':'search_health_guidance','args':{'query':'胃溃疡'},'id':'search'}])
            assert 'ulcer-diet' in messages[-1].content
            return AIMessage(content=json.dumps({'summary':'资料不支持用特殊饮食治疗溃疡。','suggestions':[],'citations':['ulcer-diet']}))
    monkeypatch.setattr(agent,'ChatOpenAI',Fake)
    response=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'请检索相关资料','share_context':True}).json()
    assert response['mode']=='live'
    citation=response['citations'][0];assert citation['url'].startswith('https://www.niddk.nih.gov/')
    assert c.get('/api/v1/assistant/history').json()[0]['answer']['citations']==response['citations']
    assert 'ulcer-diet' in c.get('/api/v1/account/export').text

def test_fabricated_citation_rolls_back_plan_and_returns_only_trusted_sources(clients,monkeypatch):
    import app.agent as agent
    c,_,_=clients;setup(c);configure(monkeypatch)
    class Fake:
        def __init__(self,**kw):self.n=0
        def bind_tools(self,tools):return self
        async def ainvoke(self,messages):
            self.n+=1
            if self.n==1:return AIMessage(content='',tool_calls=[{'name':'propose_plan','args':{},'id':'draft'}])
            return AIMessage(content=json.dumps({'summary':'未经证据支持的回答','suggestions':[],'citations':['invented-source']}))
    monkeypatch.setattr(agent,'ChatOpenAI',Fake)
    r=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'胃溃疡吃什么','share_context':True}).json()
    assert r['mode']=='knowledge_fallback' and r['error_code']=='invalid_citation'
    assert '未经证据支持' not in r['summary']
    assert all(s['id']!='invented-source' for s in r['citations'])
    assert c.get('/api/v1/adjustments',params={'date':DAY}).json()==[]

def test_urgent_message_does_not_invoke_model_or_create_plan(clients,monkeypatch):
    import app.agent as agent
    c,_,_=clients;setup(c);configure(monkeypatch)
    def never(**kwargs):raise AssertionError('Must not call external model')
    monkeypatch.setattr(agent,'ChatOpenAI',never)
    r=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'我吐血了，帮我安排未来三天的饮食','share_context':True}).json()
    assert r['mode']=='health_guidance' and not r['batches']
    assert '立即就医' in r['summary']
