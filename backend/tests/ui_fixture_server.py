"""Isolated UI fixture server; synthetic model, no production DB or provider call."""
import os,sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'backend'))
os.environ['DATABASE_URL']='sqlite:///'+str(root/'work/ui-chat-fixture.db')
os.environ['LLM_MODE']='demo'
os.environ['LLM_API_KEY']='synthetic-key-not-used'
from app.db import Base,engine,SessionLocal
from app.main import app
import app.main as main
import app.vision as vision
from app.seed import seed
from langchain_core.messages import AIMessage
Base.metadata.create_all(engine)
with SessionLocal() as db:seed(db)
class FakeVision:
    def __init__(self,**kwargs):pass
    async def ainvoke(self,messages):
        return AIMessage(content=json.dumps({'summary':'测试替身：疑似米饭及混合菜，请核对','foods':[{'name':'米饭','food_id':169757,'grams':150,'confidence':'medium','reason':'合成测试匹配'},{'name':'混合菜','food_id':None,'grams':100,'confidence':'low','reason':'成分未知'}],'uncertainties':['合成测试，不代表真实图片准确率']}))
vision.ChatOpenAI=FakeVision
async def fake_photo(*args,**kwargs):
    os.environ['LLM_MODE']='live'
    try:return await vision.analyze_photo(*args,**kwargs)
    finally:os.environ['LLM_MODE']='demo'
main.analyze_photo=fake_photo
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8001,access_log=False)
