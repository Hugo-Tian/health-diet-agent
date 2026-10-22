from datetime import date
import pytest
from sqlalchemy import select,func
from app.models import Food,User,FoodLog,FoodLogItem,DailyPlan,Session,Profile,AdjustmentProposal
from app import services as s
from conftest import setup,register,revision,propose,confirm,addlog,DAY

def test_complete_loop_and_idempotency(clients):
    c,_,db=clients;setup(c)
    p=propose(c)
    assert c.get('/api/v1/plans',params={'date':DAY}).json()['active'] is None
    plan=confirm(c,p).json();assert plan['version']==1
    assert confirm(c,p).json()['id']==plan['id']
    addlog(c)
    feedback=c.post('/api/v1/feedback/generate',json={'date':DAY}).json()
    assert feedback['data_revision']==revision(c)
    r=c.post('/api/v1/adjustments/propose',json={'date':DAY,'revision':revision(c),'meal':'晚餐'})
    assert r.status_code==200,r.text
    assert confirm(c,r.json()).json()['version']==2
    assert c.get('/api/v1/daily-summary',params={'date':DAY}).json()['actual']['known']['kcal']==174

def test_cross_user_resources_export_and_delete(clients):
    a,b,_=clients;setup(a);register(b,'b@example.com')
    proposal=propose(a);plan=confirm(a,proposal).json();log=addlog(a)
    assert b.post(f"/api/v1/adjustments/{proposal['id']}/confirm").status_code==404
    assert b.post(f"/api/v1/plans/{plan['id']}/replacement-proposals",json={'date':DAY,'revision':0,'meal':'晚餐'}).status_code==404
    assert b.delete(f"/api/v1/food-logs/{log['id']}?revision=0").status_code==404
    assert not b.get('/api/v1/account/export').json()['food_logs']
    assert a.delete(f'/api/v1/account?revision={revision(a)}&confirm=DELETE').status_code==200
    assert a.get('/api/v1/profile').status_code==401
    assert b.get('/api/v1/profile').status_code==200

def test_stale_draft_after_log_change_and_profile_cas(clients):
    c,_,_=clients;setup(c);p=propose(c);addlog(c)
    assert confirm(c,p).status_code==409
    data=c.get('/api/v1/profile').json()
    assert c.patch('/api/v1/profile',json={'revision':0,'profile':data['profile']}).status_code==409

def test_two_drafts_one_active_and_reject(clients):
    c,_,_=clients;setup(c);p=propose(c);q=propose(c)
    assert confirm(c,p).status_code==200
    assert confirm(c,q).status_code==409
    r=propose(c);assert c.post(f"/api/v1/adjustments/{r['id']}/reject").status_code==200
    assert confirm(c,r).status_code==409
    assert len(c.get('/api/v1/plans',params={'date':DAY}).json()['history'])==1

def test_allergy_generation_replacement_confirmation(clients):
    c,_,factory=clients;setup(c,allergens=['蛋','大豆','鱼','甲壳类','乳'],diet='纯素')
    p=propose(c)
    assert all(not set(i['allergens']).intersection({'蛋','大豆','鱼','甲壳类','乳'}) for i in p['items'])
    assert confirm(c,p).status_code==200
    r=c.post('/api/v1/adjustments/propose',json={'date':DAY,'revision':revision(c),'meal':'晚餐','food_id':13})
    assert r.status_code==422
    q=propose(c)
    with factory() as db:
        food=db.get(Food,q['items'][0]['food_id']);food.allergens=['未知'];db.commit()
    assert confirm(c,q).status_code==422

def test_unsupported_allergen_blocks_unknown_safety(clients):
    c,_,_=clients;setup(c,allergens=['芥末'])
    assert c.post('/api/v1/plans/generate',json={'date':DAY,'revision':revision(c)}).status_code==422

def test_eaten_meal_locked(clients):
    c,_,_=clients;setup(c);confirm(c,propose(c));addlog(c)
    assert c.post('/api/v1/adjustments/propose',json={'date':DAY,'revision':revision(c),'meal':'午餐'}).status_code==409

def test_pending_unknown_and_edit_delete(clients):
    c,_,_=clients;setup(c)
    addlog(c,status='pending',finished='unknown',items=[{'name':'未知菜','grams':None}])
    unknown=addlog(c,items=[{'name':'自定义食物','grams':100}])
    known=addlog(c)
    summary=c.get('/api/v1/daily-summary',params={'date':DAY}).json()
    assert summary['pending_count']==1
    assert summary['actual']['known']['kcal']==174
    assert summary['actual']['missing']['kcal']==1
    assert not summary['actual']['complete']
    old=c.post('/api/v1/feedback/generate',json={'date':DAY}).json()
    r=c.patch(f"/api/v1/food-logs/{known['id']}",json={'revision':revision(c),'eaten_at':DAY+'T12:00:00+08:00','meal':'午餐','finished':'yes','status':'confirmed','items':[{'food_id':1,'grams':100}]})
    assert r.status_code==200
    assert c.get('/api/v1/daily-summary',params={'date':DAY}).json()['actual']['known']['kcal']==116
    assert c.post('/api/v1/feedback/generate',json={'date':DAY}).json()['data_revision']>old['data_revision']
    assert c.delete(f"/api/v1/food-logs/{known['id']}?revision={revision(c)}").status_code==200
    assert c.get('/api/v1/daily-summary',params={'date':DAY}).json()['actual']['missing']['kcal']==1

def test_timezone_cross_day_and_utc_storage(clients):
    c,_,_=clients;setup(c,timezone='America/Los_Angeles')
    log=addlog(c,eaten_at='2026-10-18T01:00:00+08:00')
    assert log['date']=='2026-10-17'
    assert log['eaten_at'].startswith('2026-10-17T17:00:00')
    assert not c.get('/api/v1/food-logs',params={'date':DAY}).json()

def test_snapshots_survive_food_changes_and_note_edits(clients):
    c,_,factory=clients;setup(c);plan=confirm(c,propose(c)).json();log=addlog(c)
    with factory() as db:
        f=db.get(Food,1);f.nutrients={'kcal':999,'protein':0,'carbs':0,'fat':0};db.commit()
    assert c.get('/api/v1/daily-summary',params={'date':DAY}).json()['actual']['known']['kcal']==174
    assert c.get('/api/v1/plans',params={'date':DAY}).json()['active']==plan
    r=c.patch(f"/api/v1/food-logs/{log['id']}",json={'revision':revision(c),'eaten_at':DAY+'T12:00:00+08:00','meal':'午餐','finished':'yes','status':'confirmed','note':'补充备注','items':[{'food_id':1,'grams':150}]})
    assert r.json()['items'][0]['nutrients']['kcal']==174

def test_units_raw_cooked_and_unknown(clients):
    _,_,factory=clients
    with factory() as db:
        cooked=s.snapshot(db.get(Food,1),150);raw=s.snapshot(db.get(Food,34),150);unknown=s.snapshot(db.get(Food,35),150)
    assert cooked['nutrients']['kcal']==174 and raw['nutrients']['kcal']==519
    assert cooked['state']=='熟重' and raw['state']=='生重'
    total=s.total([cooked,unknown]);assert not total['complete'] and total['missing']['kcal']==1

def test_csrf_and_bad_origin(clients):
    c,_,_=clients;setup(c)
    c.headers.pop('X-CSRF-Token')
    assert c.post('/api/v1/plans/generate',json={'date':DAY,'revision':revision(c)}).status_code==403
    assert c.post('/api/v1/auth/login',headers={'Origin':'https://evil.example'},json={'email':'a@example.com','password':'test-password-123'}).status_code==403

def test_restricted_targets(clients):
    c,_,_=clients;setup(c,special=['孕哺期'])
    assert c.post('/api/v1/targets/preview',json={'revision':revision(c),'lower':1800,'upper':2200}).status_code==422
    p=propose(c);assert '专业人员' in p['reason']

def test_delete_cascades_all_user_data(clients):
    c,_,factory=clients;setup(c);confirm(c,propose(c));addlog(c)
    assert c.delete(f'/api/v1/account?revision={revision(c)}&confirm=DELETE').status_code==200
    with factory() as db:
        for model in (User,Session,Profile,DailyPlan,FoodLog,FoodLogItem,AdjustmentProposal):
            assert db.scalar(select(func.count()).select_from(model))==0
        assert db.scalar(select(func.count()).select_from(Food))==35

def test_two_sessions_same_account_share_server_state(clients):
    a,b,_=clients;setup(a)
    r=b.post('/api/v1/auth/login',json={'email':'a@example.com','password':'test-password-123'}).json();b.headers['X-CSRF-Token']=r['csrf']
    old=revision(b);confirm(a,propose(a))
    assert b.get('/api/v1/plans',params={'date':DAY}).json()['active']['version']==1
    assert b.post('/api/v1/plans/generate',json={'date':DAY,'revision':old}).status_code==409

def test_invalid_log_does_not_advance_revision(clients):
    c,_,_=clients;setup(c);before=revision(c)
    r=c.post('/api/v1/food-logs',json={'revision':before,'eaten_at':DAY+'T12:00:00Z','meal':'午餐','status':'confirmed','finished':'unknown','items':[{'food_id':1,'grams':100}]})
    assert r.status_code==422 and revision(c)==before

def test_langchain_demo_tools_and_proposal(clients):
    c,_,_=clients;setup(c)
    r=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'帮我生成今天的计划'}).json()
    assert r['mode']=='demo' and 'get_profile' in r['tool_trace'] and 'propose_plan' in r['tool_trace']
    assert r['requires_confirmation'] and len(r['proposals'])==1
    assert c.get('/api/v1/plans',params={'date':DAY}).json()['active'] is None

def test_live_no_key_and_consent_fallback(clients,monkeypatch):
    c,_,_=clients;setup(c);monkeypatch.setenv('LLM_MODE','live');monkeypatch.delenv('LLM_API_KEY',raising=False)
    assert c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'今天吃了什么'}).json()['mode']=='consent_required'
    assert c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'今天吃了什么','share_context':True}).json()['mode']=='fallback'

def test_live_langchain_tool_protocol(clients,monkeypatch):
    from langchain_core.messages import AIMessage
    import app.agent as agent
    c,_,_=clients;setup(c);monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setenv('LLM_MODEL','test-model')
    class FakeModel:
        def __init__(self,**kwargs): self.n=0
        def bind_tools(self,tools): return self
        async def ainvoke(self,messages):
            self.n+=1
            if self.n==1: return AIMessage(content='',tool_calls=[{'name':'get_food_logs','args':{},'id':'call1'}])
            return AIMessage(content='{"summary":"请补全记录","suggestions":["核对实际份量"]}')
    monkeypatch.setattr(agent,'ChatOpenAI',FakeModel)
    r=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'看看记录','share_context':True}).json()
    assert r['mode']=='live' and r['tool_trace']==['get_food_logs']

def test_live_malformed_response_rolls_back_draft(clients,monkeypatch):
    from langchain_core.messages import AIMessage
    import app.agent as agent
    c,_,_=clients;setup(c);monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setenv('LLM_MODEL','test-model')
    class FakeModel:
        def __init__(self,**kwargs): self.n=0
        def bind_tools(self,tools): return self
        async def ainvoke(self,messages):
            self.n+=1
            if self.n==1:return AIMessage(content='',tool_calls=[{'name':'propose_plan','args':{},'id':'call1'}])
            return AIMessage(content='invalid response')
    monkeypatch.setattr(agent,'ChatOpenAI',FakeModel)
    r=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'生成计划','share_context':True}).json()
    assert r['mode']=='fallback' and not r['proposals']
    assert not c.get('/api/v1/adjustments',params={'date':DAY}).json()

def test_model_candidate_uses_library_numbers_and_constraints(clients):
    from app.agent import build_tools
    c,_,factory=clients;setup(c)
    candidate=[{'meal':m,'food_id':f,'grams':g} for m in ['早餐','午餐','晚餐'] for f,g in [(1,150),(9,100),(17,150)]]
    with factory() as db:
        user=db.scalar(select(User));tools={t.name:t for t in build_tools(db,user,date.fromisoformat(DAY))}
        result=tools['propose_plan'].invoke({'items':candidate})
        assert result['items'][0]['nutrients']['kcal']==174
        assert result['status']=='pending'
        db.rollback()
        with pytest.raises(Exception): tools['propose_plan'].invoke({'items':[{'meal':'早餐','food_id':1,'grams':100,'kcal':1}]})
        with pytest.raises(Exception): tools['propose_plan'].invoke({'items':candidate[:3]})

def test_concurrent_confirm_never_creates_two_versions(clients):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from app.main import app
    a,b,factory=clients;setup(a)
    r=b.post('/api/v1/auth/login',json={'email':'a@example.com','password':'test-password-123'}).json();b.headers['X-CSRF-Token']=r['csrf']
    p=propose(a);barrier=Barrier(2)
    def perform(c): barrier.wait();return confirm(c,p).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(perform,[a,b]))
    assert 200 in outcomes and all(code in (200,409) for code in outcomes)
    assert confirm(a,p).status_code==200
    with factory() as db: assert db.scalar(select(func.count()).select_from(DailyPlan))==1

def test_confirmation_cannot_be_overwritten_by_rejection(clients):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    a,b,factory=clients;setup(a)
    r=b.post('/api/v1/auth/login',json={'email':'a@example.com','password':'test-password-123'}).json();b.headers['X-CSRF-Token']=r['csrf']
    p=propose(a);barrier=Barrier(2)
    def do_confirm(): barrier.wait();return confirm(a,p).status_code
    def do_reject(): barrier.wait();return b.post(f"/api/v1/adjustments/{p['id']}/reject").status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(do_confirm);second=pool.submit(do_reject);results=[first.result(),second.result()]
    with factory() as db:
        row=db.get(AdjustmentProposal,p['id']);count=db.scalar(select(func.count()).select_from(DailyPlan))
        assert (row.status=='confirmed' and count==1) or (row.status=='rejected' and count==0)

def test_profile_restriction_removes_previous_target(clients):
    c,_,_=clients;p=setup(c)
    assert c.post('/api/v1/targets/confirm',json={'revision':revision(c),'lower':1800,'upper':2200,'confirmed':True}).status_code==200
    p['special']=['孕哺期']
    response=c.patch('/api/v1/profile',json={'revision':revision(c),'profile':p})
    assert response.status_code==200 and response.json()['target'] is None

def test_deepseek_provider_options(monkeypatch):
    from app.agent import provider_options
    monkeypatch.setenv('LLM_BASE_URL','https://api.deepseek.com')
    assert provider_options()=={'extra_body':{'thinking':{'type':'disabled'}}}
    monkeypatch.setenv('LLM_BASE_URL','https://example.com/v1')
    assert provider_options()=={}
