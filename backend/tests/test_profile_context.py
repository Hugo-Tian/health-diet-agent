import json
from datetime import timedelta
from langchain_core.messages import AIMessage,SystemMessage
from conftest import setup,DAY,revision

def test_each_request_receives_current_profile_system_message(clients,monkeypatch):
    import app.agent as agent
    c,_,_=clients;setup(c,height_cm=175,weight_kg=70,allergens=['花生'])
    monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setenv('LLM_MODEL','test')
    contexts=[]
    class Fake:
        def __init__(self,**kwargs):self.n=0
        def bind_tools(self,tools):return self
        async def ainvoke(self,messages):
            assert isinstance(messages[1],SystemMessage)
            context=json.loads(messages[1].content.split('\n',1)[1]);contexts.append(context)
            assert 'password' not in messages[1].content and 'a@example.com' not in messages[1].content
            self.n+=1
            if self.n==1:return AIMessage(content='',tool_calls=[{'name':'get_food_logs','args':{},'id':'read'}])
            return AIMessage(content='{"summary":"已结合最新档案回答","suggestions":[]}')
    monkeypatch.setattr(agent,'ChatOpenAI',Fake)
    def ask():
        r=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'结合我的情况看看记录','share_context':True})
        assert r.json()['mode']=='live'
    ask();assert contexts[-1]['profile']['weight_kg']==70 and contexts[-1]['profile']['allergens']==['花生']
    p=c.get('/api/v1/profile').json()['profile'];p['weight_kg']=72
    assert c.patch('/api/v1/profile',json={'revision':revision(c),'profile':p}).status_code==200
    ask();assert contexts[-1]['profile']['weight_kg']==72 and contexts[-1]['data_revision']>contexts[0]['data_revision']

def test_model_tool_creates_dated_plan_card_and_confirmation(clients,monkeypatch):
    import app.agent as agent
    from datetime import date
    c,_,_=clients;setup(c)
    target=(date.fromisoformat(c.get('/api/v1/profile').json()['today'])+timedelta(days=1)).isoformat()
    monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setenv('LLM_MODEL','test')
    class Fake:
        def __init__(self,**kwargs):self.n=0
        def bind_tools(self,tools):return self
        async def ainvoke(self,messages):
            self.n+=1
            if self.n==1:return AIMessage(content='',tool_calls=[{'name':'propose_plan','args':{'plan_date':target},'id':'create'}])
            return AIMessage(content='{"summary":"已生成明天计划草案，请查看卡片确认","suggestions":[]}')
    monkeypatch.setattr(agent,'ChatOpenAI',Fake)
    r=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'建立明天计划','share_context':True}).json()
    assert r['mode']=='live' and len(r['proposals'])==1
    card=r['proposals'][0];assert card['date']==target and len(card['items'])==9 and card['totals']['known']['kcal']>0
    assert c.get('/api/v1/plans',params={'date':target}).json()['active'] is None
    assert c.get('/api/v1/assistant/history').json()[0]['answer']['proposals'][0]['id']==card['id']
    assert c.post(f"/api/v1/adjustments/{card['id']}/confirm").status_code==200
    assert c.get('/api/v1/plans',params={'date':target}).json()['active']['items']==card['items']

def test_failed_batch_can_be_corrected_without_orphan_drafts(clients,monkeypatch):
    import app.agent as agent
    from datetime import date
    from sqlalchemy import select,func
    from app.models import AdjustmentProposal
    c,_,factory=clients;setup(c)
    today=date.fromisoformat(c.get('/api/v1/profile').json()['today'])
    dates=[(today+timedelta(days=i)).isoformat() for i in [1,2]]
    monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setenv('LLM_MODEL','test')
    class Fake:
        def __init__(self,**kwargs):self.n=0
        def bind_tools(self,tools):return self
        async def ainvoke(self,messages):
            self.n+=1
            if self.n<=2:
                days=[{'date':d} for d in dates]
                if self.n==1:days[1]['items']=[{'meal':'早餐','food_id':9999999,'grams':100}]
                else:assert 'error' in json.loads(messages[-1].content)
                return AIMessage(content='',tool_calls=[{'name':'propose_future_plans','args':{'plans':days},'id':str(self.n)}])
            return AIMessage(content='{"summary":"两日草案已生成，请确认","suggestions":[]}')
    monkeypatch.setattr(agent,'ChatOpenAI',Fake)
    r=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'建立两天计划','share_context':True}).json()
    assert r['mode']=='live' and len(r['batches'][0]['proposals'])==2
    assert 'propose_future_plans:validation_error' in r['tool_trace']
    with factory() as db:assert db.scalar(select(func.count()).select_from(AdjustmentProposal))==2
