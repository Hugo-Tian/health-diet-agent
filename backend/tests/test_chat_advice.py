import pytest
from langchain_core.messages import AIMessage
from app.agent import has_restrictive_advice
from conftest import setup,DAY

@pytest.mark.parametrize('text',[
    '你提到最近作息不规律，每天只吃了两顿饭。',
    '不建议跳餐，也不要通过跳餐来补偿。',
    '不应该服用减肥药来解决作息问题。',
    '避免每天只吃一顿，先恢复规律进餐。',
])
def test_description_and_negation_are_not_restrictive_advice(text):
    assert not has_restrictive_advice(text)

@pytest.mark.parametrize('text',['建议跳餐','你可以通过跳餐来补偿','请每天只吃一顿','建议服用减肥药'])
def test_affirmative_restrictive_advice_is_rejected(text):
    assert has_restrictive_advice(text)

def test_two_meal_question_accepts_normal_live_answer(clients,monkeypatch):
    import app.agent as agent
    c,_,_=clients;setup(c)
    monkeypatch.setenv('LLM_MODE','live');monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setenv('LLM_MODEL','test-model')
    class Fake:
        def __init__(self,**kwargs):self.n=0
        def bind_tools(self,tools):return self
        async def ainvoke(self,messages):
            self.n+=1
            if self.n==1:return AIMessage(content='',tool_calls=[{'name':'get_recent_food_logs','args':{},'id':'read1'}])
            return AIMessage(content='{"summary":"你说最近每天只吃了两顿饭，先从规律进餐开始。","suggestions":["不建议跳餐来补偿。","补充记录实际吃的食物与份量。"]}')
    monkeypatch.setattr(agent,'ChatOpenAI',Fake)
    r=c.post('/api/v1/assistant/messages',json={'date':DAY,'message':'我最近作息不规律，每天只吃了两顿饭，该怎么办','share_context':True}).json()
    assert r['mode']=='live' and not r.get('error') and not r['proposals'] and not r['batches']
    assert c.get('/api/v1/assistant/history').json()[0]['answer']['mode']=='live'
