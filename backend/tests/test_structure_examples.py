from datetime import timedelta
import pytest
from sqlalchemy import select
from app.models import User,Profile
from app.agent import build_tools
from app import services as s
from conftest import setup,DAY

def test_restricted_profile_gets_seven_pending_structure_cards(clients):
    c,_,factory=clients;setup(c)
    with factory() as db:
        user=db.scalar(select(User));row=db.get(Profile,user.id)
        row.data={**row.data,'special':['治疗性饮食']};db.commit()
        tool=next(t for t in build_tools(db,user,DAY) if t.name=='propose_structure_examples')
        batch=tool.invoke({'days':7})
        assert batch['status']=='pending' and batch['requires_confirmation']
        today=s.local_today(s.profile_data(db,user))
        assert [p['date'] for p in batch['proposals']]==[today+timedelta(days=i) for i in range(1,8)]
        for p in batch['proposals']:
            assert len(p['items'])==9
            assert '份量为示例' in p['reason']
            assert s.active_plan(db,user,p['date']) is None
            for meal in ('早餐','午餐','晚餐'):
                assert {i['group'] for i in p['items'] if i['meal']==meal}=={'主食','蛋白','蔬菜'}
        with pytest.raises(ValueError):
            tool.invoke({'days':8})
