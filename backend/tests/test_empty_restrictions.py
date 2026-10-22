import pytest
from sqlalchemy import select
from app.models import User,Profile
from app.schemas import ProfileData
from app.agent import build_tools
from app.catalog import import_catalog
from app import services as s
from conftest import setup,DAY

@pytest.mark.parametrize('marker',['无',' 无 ','没有','none','None','无过敏原','无忌口'])
def test_absence_markers_are_empty_constraints(marker):
    p=ProfileData(allergens=[marker],exclusions=[marker])
    assert p.allergens==[] and p.exclusions==[]

def test_real_and_unknown_allergens_are_preserved():
    assert ProfileData(allergens=['无','花生','未知']).allergens==['花生','未知']
    assert ProfileData(exclusions=['无','牛肉']).exclusions==['牛肉']

def test_legacy_none_profile_can_search_without_modifying_stored_data(clients):
    c,_,factory=clients;setup(c)
    with factory() as db:
        import_catalog(db)
        user=db.scalar(select(User));row=db.get(Profile,user.id)
        row.data={**row.data,'allergens':['无'],'exclusions':['无']};db.commit()
        tool=next(t for t in build_tools(db,user,DAY) if t.name=='search_food')
        result=tool.invoke({})
        assert result['status']=='matched' and result['catalog_count']==79
        assert result['eligible_count']>0 and len(result['foods'])==result['matched_count']
        assert row.data['allergens']==['无']
    p=c.get('/api/v1/profile').json()['profile'];assert p['allergens']==[] and p['exclusions']==[]

def test_search_distinguishes_constraints_and_name_mismatch(clients):
    c,_,factory=clients;setup(c)
    with factory() as db:
        user=db.scalar(select(User));tool=next(t for t in build_tools(db,user,DAY) if t.name=='search_food')
        r=tool.invoke({'query':'a-food-that-does-not-exist'})
        assert r['status']=='no_name_match' and r['eligible_count']>0 and not r['foods']
        row=db.get(Profile,user.id);row.data={**row.data,'allergens':['芥末']};db.commit()
        r=tool.invoke({})
        assert r['status']=='constraints_blocked' and r['catalog_count']>0 and not r['foods']
