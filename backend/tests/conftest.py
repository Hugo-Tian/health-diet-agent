import os
import pytest
from sqlalchemy import create_engine,event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db import Base,get_db
from app.main import app
from app.seed import seed_demo as seed
from app.security import attempts

@pytest.fixture
def clients(tmp_path,monkeypatch):
    monkeypatch.setenv('LLM_MODE','demo')
    engine=create_engine('sqlite:///'+str(tmp_path/'test.db'),connect_args={'check_same_thread':False})
    @event.listens_for(engine,'connect')
    def fk(conn,_): conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    with factory() as db: seed(db)
    def override():
        with factory() as db: yield db
    app.dependency_overrides[get_db]=override
    attempts.clear()
    a,b=TestClient(app),TestClient(app)
    yield a,b,factory
    a.close();b.close();app.dependency_overrides.clear();engine.dispose()

def register(c,email='a@example.com'):
    r=c.post('/api/v1/auth/register',json={'email':email,'password':'test-password-123'})
    assert r.status_code==200,r.text
    c.headers['X-CSRF-Token']=r.json()['csrf']
    return r.json()

def revision(c): return c.get('/api/v1/profile').json()['revision']

def setup(c,**changes):
    register(c)
    p=c.get('/api/v1/profile').json()['profile']
    p.update(adult=True,age=25,goal_confirmed=True,**changes)
    r=c.patch('/api/v1/profile',json={'revision':revision(c),'profile':p})
    assert r.status_code==200,r.text
    return p

DAY='2026-10-18'

def propose(c):
    r=c.post('/api/v1/plans/generate',json={'date':DAY,'revision':revision(c)})
    assert r.status_code==200,r.text
    return r.json()

def confirm(c,p): return c.post(f"/api/v1/adjustments/{p['id']}/confirm")

def addlog(c,**changes):
    data={'revision':revision(c),'eaten_at':DAY+'T12:00:00+08:00','meal':'午餐','status':'confirmed','finished':'yes','items':[{'food_id':1,'grams':150}]}
    data.update(changes)
    r=c.post('/api/v1/food-logs',json=data)
    assert r.status_code==200,r.text
    return r.json()
