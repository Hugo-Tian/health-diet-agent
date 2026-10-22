import json
from pathlib import Path
from sqlalchemy import select,delete,update
from .models import Food,Portion,User

CATALOG=Path(__file__).resolve().parents[1]/'data'/'usda_catalog.json'

def import_catalog(db):
    """Transactional, repeatable import; existing plan/log snapshots are never touched."""
    data=json.loads(CATALOG.read_text(encoding='utf-8'))
    changed=0
    for entry in data['foods']:
        f=db.get(Food,entry['id'])
        values={k:entry[k] for k in ('name','group','state','nutrients','allergens','tags','provenance')}
        values.update(active=True,version=data['version'],source=f"USDA FoodData Central · SR Legacy · FDC {entry['id']}")
        if f and all(getattr(f,k)==v for k,v in values.items()):continue
        if f is None:
            f=Food(id=entry['id'],**values);db.add(f);db.flush()
        else:
            if not f.version.startswith('usda-'): raise ValueError('Food ID collision')
            for k,v in values.items():setattr(f,k,v)
        db.execute(delete(Portion).where(Portion.food_id==f.id))
        for p in entry['portions']:db.add(Portion(food_id=f.id,**p))
        changed+=1
    for f in db.scalars(select(Food).where(Food.active==True,Food.version.like('demo-%'))):
        f.active=False;changed+=1
    if changed:
        # Stale pending proposals and cached feedback must not silently survive a catalog revision.
        db.execute(update(User).values(revision=User.revision+1))
    db.commit()
    return {'reference_foods':len(data['foods']),'changed_rows':changed,'version':data['version']}
