from datetime import timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, update, func
from .db import utcnow
from .models import *
from .schemas import ProfileData
from .security import fail

KEYS = ('kcal', 'protein', 'carbs', 'fat', 'fiber', 'sodium_mg', 'calcium_mg', 'iron_mg', 'potassium_mg')
MEALS = ('早餐', '午餐', '晚餐', '加餐')

def profile_data(db, user):
    p = db.get(Profile, user.id)
    return ProfileData.model_validate(p.data if p else {}).model_dump()

def local_today(profile):
    return utcnow().astimezone(ZoneInfo(profile['timezone'])).date()

def restricted(profile):
    return not profile['adult'] or (profile['age'] is not None and profile['age'] < 18) or bool(profile['special'])

def bump(db, user, expected):
    result = db.execute(update(User).where(User.id == user.id, User.revision == expected).values(revision=expected+1), execution_options={'synchronize_session': False})
    if result.rowcount != 1: fail(409, '数据已在其他页面或设备更新，请刷新后重试', 'revision_conflict')
    user.revision = expected+1

def owner(db, model, id, user):
    row = db.scalar(select(model).where(model.id == id, model.user_id == user.id))
    if not row: fail(404, '未找到此记录', 'not_found')
    return row

def food_dict(db, f):
    portions = db.scalars(select(Portion).where(Portion.food_id == f.id)).all()
    return dict(id=f.id, name=f.name, group=f.group, state=f.state, nutrients=f.nutrients, allergens=f.allergens, tags=f.tags, source=f.source, version=f.version, demo=f.version.startswith('demo-'), active=f.active, provenance={k:v for k,v in (f.provenance or {}).items() if k!='nutrient_evidence'}, unit='每100g可食部', portions=[dict(unit=p.unit, grams=p.grams, source=p.source) for p in portions])

def snapshot(food, grams):
    return dict(food_id=food.id, name=food.name, grams=grams, state=food.state, group=food.group, nutrients={k: round(v*grams/100, 2) if v is not None and grams is not None else None for k,v in food.nutrients.items()}, source=food.source, source_version=food.version, demo=food.version.startswith('demo-'), provenance={k:v for k,v in (food.provenance or {}).items() if k!='nutrient_evidence'}, allergens=food.allergens)

def total(items):
    known = {k: round(sum(x['nutrients'].get(k) or 0 for x in items), 2) for k in KEYS}
    missing = {k: sum(x['nutrients'].get(k) is None for x in items) for k in KEYS}
    return dict(known=known, missing=missing, complete=not any(missing.values()), item_count=len(items),demo_items=sum(bool(i.get('demo')) for i in items),reference_items=sum(bool(i.get('provenance',{}).get('fdc_id')) for i in items))

ALIASES = {'牛奶':'乳','奶':'乳','乳制品':'乳','鸡蛋':'蛋','鸡蛋过敏':'蛋','豆类':'大豆','豆':'大豆','小麦':'麸质','虾':'甲壳类','蟹':'甲壳类','海鲜':'海鲜'}

def allowed(food, p):
    allergens = {ALIASES.get(a, a) for a in p['allergens']}
    supported = {'乳','蛋','大豆','麸质','甲壳类','鱼','花生','坚果','海鲜','芝麻','荞麦','芹菜'}
    if allergens - supported: return False
    if '未知' in food.allergens or 'unknown' in food.tags: return False
    if allergens.intersection(food.allergens): return False
    if '海鲜' in allergens and set(food.allergens).intersection({'鱼','甲壳类'}): return False
    if p['diet'] == '纯素' and 'vegan' not in food.tags: return False
    if p['diet'] == '蛋奶素' and 'meat' in food.tags: return False
    if any(term in food.name or term in food.tags or term in food.allergens for term in p['exclusions']): return False
    return True

def validate_items(db, items, p):
    if not items or len(items) > 30: fail(422, '计划食物数量无效')
    for item in items:
        f = db.get(Food, item['food_id'])
        if not f or not allowed(f, p): fail(422, '食物与过敏、饮食限制冲突，或成分无法验证。请修改限制或选其他食物。', 'diet_conflict')
        if item['meal'] not in MEALS or not 0 < item['grams'] <= 3000: fail(422, '餐次或份量无效')
    return True

def active_plan(db, user, date):
    state = db.scalar(select(DailyState).where(DailyState.user_id == user.id, DailyState.local_date == date))
    return db.get(DailyPlan, state.active_plan_id) if state else None

def plan_dict(db, plan):
    if not plan: return None
    items = [dict(**row.snapshot, meal=row.meal) for row in db.scalars(select(MealPlanItem).where(MealPlanItem.plan_id == plan.id).order_by(MealPlanItem.id))]
    return dict(id=plan.id, date=plan.local_date, version=plan.version, based_on_revision=plan.based_on_revision, items=items, totals=total(items))

def logs(db, user, date):
    rows = db.scalars(select(FoodLog).where(FoodLog.user_id == user.id, FoodLog.local_date == date).order_by(FoodLog.eaten_at, FoodLog.id)).all()
    return [log_dict(db, row) for row in rows]

def log_dict(db, row):
    return dict(id=row.id, date=row.local_date, eaten_at=row.eaten_at.replace(tzinfo=timezone.utc), meal=row.meal, status=row.status, finished=row.finished, note=row.note, items=[i.snapshot for i in db.scalars(select(FoodLogItem).where(FoodLogItem.log_id == row.id).order_by(FoodLogItem.id))])

def eaten_meals(db, user, date):
    return {r['meal'] for r in logs(db, user, date) if r['status'] == 'confirmed'}

def summary(db, user, date):
    rows = logs(db, user, date)
    items = [i for r in rows if r['status'] == 'confirmed' for i in r['items']]
    return dict(date=date, data_revision=user.revision, actual=total(items), pending_count=sum(r['status'] != 'confirmed' for r in rows), confirmed_count=sum(r['status'] == 'confirmed' for r in rows), recorded_meals=sorted({r['meal'] for r in rows if r['status'] == 'confirmed'}), planned=plan_dict(db, active_plan(db, user, date)))

def structure_items(db, user, date):
    p = profile_data(db, user)
    foods = [f for f in db.scalars(select(Food).where(Food.active==True).order_by(Food.id)) if allowed(f,p) and f.state != '生重' and f.group != '坚果']
    result = []
    for index, meal in enumerate(MEALS[:3]):
        for group, grams in [('主食',150), ('蛋白',100), ('蔬菜',150)]:
            choices = [f for f in foods if f.group == group]
            if not choices: fail(422, '食物库中没有符合全部限制的餐食组合，请完善食物库或检查限制。', 'no_safe_food')
            preferred = [f for f in choices if f.name in p['preferences']]
            chosen = (preferred or choices)[(index + date.toordinal()) % len(preferred or choices)]
            result.append(dict(**snapshot(chosen, grams), meal=meal))
    return result

def proposal_dict(db, proposal):
    return dict(id=proposal.id, date=proposal.local_date, base_plan_id=proposal.base_plan_id, base_data_revision=proposal.base_data_revision, items=proposal.payload, before=plan_dict(db, db.get(DailyPlan, proposal.base_plan_id)) if proposal.base_plan_id else None, reason=proposal.reason, status=proposal.status, result_plan_id=proposal.result_plan_id, totals=total(proposal.payload))

def create_proposal(db, user, date, revision, meal=None, food_id=None, replace_food_id=None):
    if revision != user.revision: fail(409, '请刷新最新数据后再生成草案', 'revision_conflict')
    p = profile_data(db, user)
    if not p['goal_confirmed']: fail(422, '请先在档案中确认饮食目标', 'profile_incomplete')
    base = active_plan(db, user, date)
    eaten = eaten_meals(db, user, date)
    if meal:
        if not base: fail(422, '请先生成并确认当天计划')
        if meal in eaten: fail(409, '已记录吃过的餐次不能修改', 'meal_locked')
        items = plan_dict(db, base)['items']
        candidates = [x for x in items if x['meal'] == meal and (replace_food_id is None or x['food_id'] == replace_food_id)]
        if not candidates: fail(422, '未找到待替换食物')
        old = candidates[0]
        choices = [f for f in db.scalars(select(Food).where(Food.group == old['group'],Food.active==True).order_by(Food.id)) if allowed(f,p) and f.state != '生重' and f.id != old['food_id']]
        chosen = db.get(Food, food_id) if food_id else (choices[0] if choices else None)
        if not chosen: fail(422, '没有可替换食物，请选择其他食物')
        if not chosen.active: fail(422,'此食物已归档，仅用于解释旧记录，请选择当前食物库中的条目')
        items = [dict(**snapshot(chosen, old['grams']), meal=meal) if x is old else x for x in items]
        reason = f'{meal}食物替换，仅修改未吃餐次；不是根据单餐偏差调整长期目标。'
    else:
        items = structure_items(db, user, date)
        if eaten and not base: fail(409, '当天已有摄入记录，请选择其他日期建立计划，避免改写已吃餐次')
        if base:
            items = [x for x in items if x['meal'] not in eaten] + [x for x in plan_dict(db, base)['items'] if x['meal'] in eaten]
        reason = '一般三餐结构建议，份量为示例，并非个性化热量处方；预算和当地供应需自行核对。'
        if restricted(p): reason += '当前适用范围仅支持记录与一般结构示例，请向专业人员咨询个体方案。'
    validate_items(db, items, p)
    proposal = AdjustmentProposal(user_id=user.id, local_date=date, base_plan_id=base.id if base else None, base_data_revision=revision, payload=items, reason=reason)
    db.add(proposal); db.flush()
    return proposal

def candidate_proposal(db,user,date,candidates):
    """Accept model food selections, recompute every numeric snapshot server-side."""
    p=profile_data(db,user)
    if restricted(p):
        fail(422,'当前服务范围只允许规则生成的一般结构示例，不接受模型个体份量方案。')
    if not p['goal_confirmed']: fail(422,'请先确认饮食目标')
    items=[]
    for candidate in candidates:
        food=db.get(Food,candidate.food_id)
        if not food or not food.active: fail(422,'候选食物不存在或已归档')
        items.append(dict(**snapshot(food,candidate.grams),meal=candidate.meal))
    validate_items(db,items,p)
    base=active_plan(db,user,date)
    eaten=eaten_meals(db,user,date)
    if eaten and not base: fail(409,'当天已存在摄入，不能重新建立已吃餐次计划')
    if base:
        items=[i for i in items if i['meal'] not in eaten]+[i for i in plan_dict(db,base)['items'] if i['meal'] in eaten]
    for meal in MEALS[:3]:
        groups={i['group'] for i in items if i['meal']==meal}
        missing={'主食','蛋白','蔬菜'}-groups
        if missing:
            fail(422,f"{date} {meal}缺少分类：{'、'.join(sorted(missing))}；当前分类：{'、'.join(sorted(groups)) or '空'}。请按search_food返回的group补足；乳豆、水果不属于当前校验的蛋白/蔬菜分类。",'meal_groups_missing')
    proposal=AdjustmentProposal(user_id=user.id,local_date=date,base_plan_id=base.id if base else None,base_data_revision=user.revision,payload=items,reason='模型候选组合，营养由参考食物库重算；尚未确认，预算和供应请自行核对，不是个性化热量处方。')
    db.add(proposal);db.flush()
    return proposal

def confirm_proposal(db, user, proposal, *, revision_locked=False):
    if proposal.status == 'confirmed': return plan_dict(db, db.get(DailyPlan, proposal.result_plan_id))
    if proposal.status != 'pending': fail(409, '该草案已拒绝', 'proposal_closed')
    if not revision_locked: bump(db, user, proposal.base_data_revision)
    base = active_plan(db, user, proposal.local_date)
    if (base.id if base else None) != proposal.base_plan_id: fail(409, '生效计划已变化，请重新生成草案', 'plan_conflict')
    validate_items(db, proposal.payload, profile_data(db, user))
    if base:
        before = plan_dict(db, base)['items']
        for meal in eaten_meals(db, user, proposal.local_date):
            if [i for i in before if i['meal']==meal] != [i for i in proposal.payload if i['meal']==meal]: fail(409, '已吃餐次不可修改', 'meal_locked')
    plan = DailyPlan(user_id=user.id, local_date=proposal.local_date, version=base.version+1 if base else 1, based_on_revision=proposal.base_data_revision)
    db.add(plan); db.flush()
    for item in proposal.payload:
        db.add(MealPlanItem(plan_id=plan.id, user_id=user.id, meal=item['meal'], snapshot={k:v for k,v in item.items() if k != 'meal'}))
    state = db.scalar(select(DailyState).where(DailyState.user_id==user.id, DailyState.local_date==proposal.local_date))
    if state: state.active_plan_id = plan.id
    else: db.add(DailyState(user_id=user.id, local_date=proposal.local_date, active_plan_id=plan.id))
    proposal.status, proposal.result_plan_id, proposal.confirmed_at = 'confirmed', plan.id, utcnow()
    db.flush()
    return plan_dict(db, plan)

def feedback_data(db, user, date):
    s = summary(db, user, date)
    return dict(summary='把已经吃的记清楚，再决定下一餐。', known_facts=[f"已确认 {s['confirmed_count']} 条记录，已知能量约 {s['actual']['known']['kcal']} kcal。", f"已记录餐次：{'、'.join(s['recorded_meals']) or '暂无'}。"], uncertainties=['营养按对应食物的来源估算；历史演示项保留标记，未知配方和用油不能凭空补齐。', f"待确认 {s['pending_count']} 条；存在未知营养的食物项 {max(s['actual']['missing'].values())} 个。"], suggestions=['优先补全实际份量与未确认记录。', '下一餐保持正常进餐，结合饥饿感安排主食、蛋白质食物和蔬菜。'], proposed_changes=[], requires_confirmation=False, data_revision=user.revision)
