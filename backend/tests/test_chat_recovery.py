from sqlalchemy import select
from langchain_core.messages import AIMessage
from app.models import User
from app.agent import build_tools
from conftest import setup,DAY

def test_multiday_validation_deduplicates_more_than_thirty_items(clients):
    c,_,factory=clients;setup(c)
    with factory() as db:
        user=db.scalar(select(User))
        tool=next(t for t in build_tools(db,user,DAY) if t.name=='validate_plan')
        result=tool.invoke({'food_ids':[1,9,17]*30})
        assert result=={'valid':True,'invalid_food_ids':[],'checked_count':3}

def test_scope_clarification_without_tool_call_is_valid_response(clients,monkeypatch):
    import app.agent as agent
    c,_,_=clients;setup(c)
    monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setenv('LLM_MODEL','test')
    class Fake:
        def __init__(self,**kwargs):pass
        def bind_tools(self,tools):return self
        async def ainvoke(self,messages):
            return AIMessage(content='{"summary":"参考资料不支持特殊饮食治疗溃疡，请说明已有医嘱，当前尚未建立计划。","suggestions":[],"citations":["ulcer-diet"]}')
    monkeypatch.setattr(agent,'ChatOpenAI',Fake)
    result=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'我有胃溃疡，帮我生成未来三天的计划','share_context':True}).json()
    assert result['mode']=='live' and result['tool_trace']==['search_health_guidance:auto']
    assert result['proposals']==[] and result['batches']==[] and not result.get('error')

def test_invalid_model_json_exposes_safe_error_code(clients,monkeypatch):
    import app.agent as agent
    c,_,_=clients;setup(c)
    monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setenv('LLM_MODEL','test')
    class Fake:
        def __init__(self,**kwargs):pass
        def bind_tools(self,tools):return self
        async def ainvoke(self,messages):return AIMessage(content='private-provider-output')
    monkeypatch.setattr(agent,'ChatOpenAI',Fake)
    r=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'看看记录','share_context':True})
    assert r.json()['error_code']=='response_schema'
    assert 'private-provider-output' not in r.text
