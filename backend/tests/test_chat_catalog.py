import base64,io,json
from datetime import timedelta
from PIL import Image
from sqlalchemy import select,func
from langchain_core.messages import AIMessage
from app.catalog import import_catalog,CATALOG
from app.models import Food,User,ChatTurn,FoodLog,DailyPlan
from app import services as s
from conftest import setup,register,revision,propose,confirm,addlog,DAY

def test_catalog_import_provenance_idempotency_history(clients):
    c,_,factory=clients;setup(c);p=confirm(c,propose(c)).json();addlog(c)
    previous=revision(c)
    with factory() as db:
        result=import_catalog(db);assert result['reference_foods']==79
        food=db.get(Food,169757)
        assert food.nutrients['kcal']==130 and food.nutrients['carbs']==28.2
        assert food.provenance['nutrient_evidence']['kcal']['nutrient']['unitName']=='kcal'
        assert not db.get(Food,1).active
        assert import_catalog(db)['changed_rows']==0
    assert revision(c)==previous+1
    catalog=c.get('/api/v1/foods?limit=100').json()
    assert len(catalog)==79 and all(not f['demo'] for f in catalog)
    assert c.get('/api/v1/daily-summary',params={'date':DAY}).json()['actual']['known']['kcal']==174
    assert c.get('/api/v1/plans',params={'date':DAY}).json()['active']==p

def test_all_imported_values_equal_official_evidence():
    data=json.loads(CATALOG.read_text(encoding='utf-8'))
    assert len({f['id'] for f in data['foods']})==79
    for food in data['foods']:
        for key,value in food['nutrients'].items():
            e=food['provenance']['nutrient_evidence'][key]
            assert value==(e.get('amount') if e else None)
            if e:assert e['nutrient']['unitName'].lower()==food['provenance']['nutrient_units'][key].lower()
        assert food['provenance']['url'].startswith('https://fdc.nal.usda.gov/')

def make_batch(c):
    response=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'请安排未来三天的计划','request_id':'batch-synthetic-01'})
    assert response.status_code==200,response.text
    return response.json()['batches'][0]

def test_chat_future_batch_confirmation_is_atomic_and_idempotent(clients):
    c,b,factory=clients;setup(c);register(b,'b@example.com')
    batch=make_batch(c)
    assert len(batch['proposals'])==3
    for p in batch['proposals']:assert c.get('/api/v1/plans',params={'date':p['date']}).json()['active'] is None
    assert b.post(f"/api/v1/assistant/batches/{batch['batch_id']}/confirm").status_code==404
    assert c.post(f"/api/v1/adjustments/{batch['proposals'][0]['id']}/confirm").status_code==409
    r=c.post(f"/api/v1/assistant/batches/{batch['batch_id']}/confirm")
    assert r.status_code==200,r.text
    assert r.json()['status']=='confirmed'
    assert c.post(f"/api/v1/assistant/batches/{batch['batch_id']}/confirm").status_code==200
    with factory() as db:assert db.scalar(select(func.count()).select_from(DailyPlan))==3
    history=c.get('/api/v1/assistant/history').json();assert history[0]['answer']['batches'][0]['status']=='confirmed'
    assert not b.get('/api/v1/assistant/history').json()

def test_stale_future_batch_no_partial_write(clients):
    c,_,factory=clients;setup(c);batch=make_batch(c);addlog(c)
    assert c.post(f"/api/v1/assistant/batches/{batch['batch_id']}/confirm").status_code==409
    with factory() as db:assert db.scalar(select(func.count()).select_from(DailyPlan))==0

def test_batch_reject_does_not_change_plan(clients):
    c,_,factory=clients;setup(c);batch=make_batch(c)
    assert c.post(f"/api/v1/assistant/batches/{batch['batch_id']}/reject").status_code==200
    assert c.post(f"/api/v1/assistant/batches/{batch['batch_id']}/confirm").status_code==409
    with factory() as db:assert db.scalar(select(func.count()).select_from(DailyPlan))==0

def test_batch_later_failure_rolls_back_earlier_day(clients,monkeypatch):
    from app.security import fail
    c,_,factory=clients;setup(c);batch=make_batch(c);previous=revision(c)
    original=s.confirm_proposal;calls=[]
    def fail_second(db,user,proposal,**kwargs):
        calls.append(proposal.id)
        if len(calls)==2:fail(409,'合成测试：第二天校验失败')
        return original(db,user,proposal,**kwargs)
    monkeypatch.setattr(s,'confirm_proposal',fail_second)
    assert c.post(f"/api/v1/assistant/batches/{batch['batch_id']}/confirm").status_code==409
    assert len(calls)==2 and revision(c)==previous
    with factory() as db:assert db.scalar(select(func.count()).select_from(DailyPlan))==0
    assert c.get('/api/v1/assistant/history').json()[0]['answer']['batches'][0]['status']=='pending'

def photo_body(c):
    buffer=io.BytesIO();Image.new('RGB',(24,24),'white').save(buffer,format='PNG')
    return {'revision':revision(c),'request_id':'photo-synthetic-01','image_data':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode(),'message':'合成照片测试','meal':'午餐','eaten_at':DAY+'T12:00:00+08:00','share_context':True}

def test_photo_pending_then_user_confirmation_and_retry(clients,monkeypatch):
    import app.vision as vision
    c,b,factory=clients;setup(c);register(b,'b@example.com');monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test-only')
    calls=[]
    class Fake:
        def __init__(self,**kwargs):pass
        async def ainvoke(self,messages):
            calls.append(messages)
            return AIMessage(content=json.dumps({'summary':'疑似米饭和混合菜','foods':[{'name':'米饭','food_id':1,'grams':150,'confidence':'medium','reason':'疑似米饭，需要核对'},{'name':'炒菜','food_id':None,'grams':100,'confidence':'low','reason':'油和食材未知'}],'uncertainties':['用油无法判断']}))
    monkeypatch.setattr(vision,'ChatOpenAI',Fake)
    body=photo_body(c);r=c.post('/api/v1/assistant/photos',json=body)
    assert r.status_code==200,r.text
    log_id=r.json()['photo_log_id'];assert log_id
    assert c.post('/api/v1/assistant/photos',json=body).json()['photo_log_id']==log_id
    assert len(calls)==1
    summary=c.get('/api/v1/daily-summary',params={'date':DAY}).json();assert summary['pending_count']==1 and summary['actual']['known']['kcal']==0
    assert b.get(f'/api/v1/food-logs/{log_id}').status_code==404
    body={'revision':revision(c),'eaten_at':DAY+'T12:00:00+08:00','meal':'午餐','status':'confirmed','finished':'yes','items':[{'food_id':1,'grams':150},{'name':'炒菜','grams':100}]}
    assert c.patch(f'/api/v1/food-logs/{log_id}',json=body).status_code==200
    summary=c.get('/api/v1/daily-summary',params={'date':DAY}).json();assert summary['actual']['known']['kcal']==174 and summary['actual']['missing']['kcal']==1
    exported=c.get('/api/v1/account/export').text;assert 'image_data' not in exported and 'base64' not in exported
    assert c.get('/api/v1/assistant/history').json()[0]['answer']['photo_status']=='confirmed'

def test_photo_invalid_image_and_no_consent_never_call_model(clients,monkeypatch):
    c,_,_=clients;setup(c);body=photo_body(c);body['share_context']=False
    assert c.post('/api/v1/assistant/photos',json=body).status_code==422
    body['share_context']=True;body['image_data']='data:image/png;base64,'+'eA=='*30
    assert c.post('/api/v1/assistant/photos',json=body).status_code==422
    assert not c.get('/api/v1/assistant/history').json()

def test_photo_model_failure_has_no_side_effects(clients,monkeypatch):
    import app.vision as vision
    c,_,factory=clients;setup(c);monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test-only');previous=revision(c)
    class Fake:
        def __init__(self,**kwargs):pass
        async def ainvoke(self,messages):return AIMessage(content='not valid JSON')
    monkeypatch.setattr(vision,'ChatOpenAI',Fake)
    assert c.post('/api/v1/assistant/photos',json=photo_body(c)).status_code==502
    assert revision(c)==previous
    with factory() as db:assert db.scalar(select(func.count()).select_from(FoodLog))==0
