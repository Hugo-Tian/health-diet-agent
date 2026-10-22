import hashlib
import json
import os
from datetime import date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends, Request, Response, Query
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, delete, inspect
from sqlalchemy.exc import IntegrityError, OperationalError
from .db import get_db
from .models import *
from .schemas import *
from .security import auth, fail, throttle, new_session, hash_password, check_password, COOKIE
from . import services as s
from .agent import run_agent
from .policy import manual_target
from . import chat_actions
from .vision import analyze_photo
from .knowledge import corpus,search_guidance

app = FastAPI(title='三餐有数 · 健康饮食 Agent',version='0.1.0')
PREFIX = '/api/v1'

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(status_code=422,content={'detail':{'code':'validation_error','message':'输入格式不正确，请检查日期、份量和必填项。','fields':['.'.join(map(str,e['loc'])) for e in exc.errors()]}})

@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(status_code=409,content={'detail':{'code':'conflict','message':'数据冲突，请刷新后重试。'}})

@app.exception_handler(OperationalError)
async def database_error(request, exc):
    return JSONResponse(status_code=503,content={'detail':{'code':'database_unavailable','message':'数据库暂时不可用，请稍后重试。'}})

@app.middleware('http')
async def privacy_headers(request, call_next):
    if request.url.path.endswith('/assistant/photos'):
        length=request.headers.get('content-length')
        if length and length.isdigit() and int(length)>6_000_000:
            return JSONResponse(status_code=413,content={'detail':{'code':'image_too_large','message':'图片请求过大，请压缩后重试'}})
    # Only same-origin browser mutations (including auth) are accepted.
    if request.method not in ('GET','HEAD','OPTIONS') and request.url.path.startswith('/api/'):
        origin = request.headers.get('origin')
        allowed_origin = os.getenv('APP_ORIGIN','').rstrip('/')
        same_origin = str(request.base_url).rstrip('/')
        if origin and origin not in {same_origin,allowed_origin}:
            return JSONResponse(status_code=403,content={'detail':{'code':'origin_rejected','message':'请求来源不匹配，请从应用页面操作。'}})
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"
    return response

@app.get(PREFIX+'/health')
def health(): return {'status':'ok','application':'health-diet-agent','mode':os.getenv('LLM_MODE','demo'),'nutrition_data':'usda-sr-2018-v1','knowledge_version':corpus()['version']}

@app.get(PREFIX+'/knowledge')
def knowledge_catalog(q: str=Query('',max_length=1000),user=Depends(auth)):
    data=corpus()
    if q.strip():return search_guidance(q)
    sources=[{**{k:v for k,v in r.items() if k not in ('aliases','questions')},'version':data['version'],
              'expired':utcnow().date()>date.fromisoformat(min(data['review_due'],r['review_due']))} for r in data['chunks']]
    return {'version':data['version'],'sources':sources,'scope':data['scope'],'method':'BM25 + 整理问法匹配 + RRF排序（本地词法检索）'}

@app.post(PREFIX+'/auth/register')
def register(body: Credentials, request: Request, response: Response, db=Depends(get_db)):
    throttle(request)
    email=body.email.lower().strip()
    if db.scalar(select(User).where(User.email==email)): fail(409,'此邮箱已注册')
    user=User(email=email,password_hash=hash_password(body.password))
    db.add(user);db.flush()
    db.add(Profile(user_id=user.id,data=ProfileData().model_dump()))
    csrf=new_session(db,user,response)
    return {'id':user.id,'csrf':csrf,'revision':user.revision}

@app.post(PREFIX+'/auth/login')
def login(body: Credentials, request: Request, response: Response, db=Depends(get_db)):
    throttle(request)
    user=db.scalar(select(User).where(User.email==body.email.lower().strip()))
    stored=user.password_hash if user else hash_password('dummy-login-password')
    valid=check_password(body.password,stored)
    if not user or not valid: fail(401,'邮箱或密码不正确')
    return {'id':user.id,'csrf':new_session(db,user,response),'revision':user.revision}

@app.get(PREFIX+'/auth/me')
def me(request: Request,user=Depends(auth)):
    return {'id':user.id,'email':user.email,'csrf':request.state.session.csrf,'revision':user.revision}

@app.post(PREFIX+'/auth/logout')
def logout(request: Request,response: Response,user=Depends(auth),db=Depends(get_db)):
    db.delete(request.state.session);db.commit();response.delete_cookie(COOKIE,path='/')
    return {'ok':True}

@app.get(PREFIX+'/profile')
def get_profile(user=Depends(auth),db=Depends(get_db)):
    p=s.profile_data(db,user)
    target=db.scalar(select(NutritionTarget).where(NutritionTarget.user_id==user.id).order_by(NutritionTarget.id.desc()))
    return {'profile':p,'revision':user.revision,'today':s.local_today(p),'restricted':s.restricted(p),'target':target.data if target else None}

@app.patch(PREFIX+'/profile')
def patch_profile(body: ProfileUpdate,user=Depends(auth),db=Depends(get_db)):
    s.bump(db,user,body.revision)
    db.get(Profile,user.id).data=body.profile.model_dump()
    if s.restricted(body.profile.model_dump()):
        db.execute(delete(NutritionTarget).where(NutritionTarget.user_id==user.id))
    db.commit()
    return get_profile(user,db)

def target_preview(body,user,db):
    return manual_target(body,s.restricted(s.profile_data(db,user)))

@app.post(PREFIX+'/targets/preview')
def preview_target(body: TargetInput,user=Depends(auth),db=Depends(get_db)):
    return target_preview(body,user,db)

@app.post(PREFIX+'/targets/confirm')
def confirm_target(body: TargetInput,user=Depends(auth),db=Depends(get_db)):
    data=target_preview(body,user,db)
    if not body.confirmed: fail(422,'请确认目标')
    s.bump(db,user,body.revision)
    db.add(NutritionTarget(user_id=user.id,data=data));db.commit()
    return data

@app.get(PREFIX+'/foods')
def foods(q: str=Query('',max_length=80),offset: int=Query(0,ge=0),limit: int=Query(50,ge=1,le=100),user=Depends(auth),db=Depends(get_db)):
    return [s.food_dict(db,f) for f in db.scalars(select(Food).where(Food.active==True,Food.name.contains(q)).order_by(Food.id).offset(offset).limit(limit))]

@app.get(PREFIX+'/foods/{id}')
def food(id: int,user=Depends(auth),db=Depends(get_db)):
    row=db.get(Food,id)
    if not row: fail(404,'未找到食物')
    return s.food_dict(db,row)

@app.get(PREFIX+'/plans')
def plan(date: date,user=Depends(auth),db=Depends(get_db)):
    active=s.plan_dict(db,s.active_plan(db,user,date))
    history=db.scalars(select(DailyPlan).where(DailyPlan.user_id==user.id,DailyPlan.local_date==date).order_by(DailyPlan.version.desc()).limit(50)).all()
    return {'active':active,'history':[s.plan_dict(db,x) for x in history]}

@app.post(PREFIX+'/plans/generate')
def generate(body: PlanRequest,user=Depends(auth),db=Depends(get_db)):
    proposal=s.create_proposal(db,user,body.date,body.revision)
    db.commit();return s.proposal_dict(db,proposal)

@app.post(PREFIX+'/plans/{id}/replacement-proposals')
def replace(id: int,body: Replacement,user=Depends(auth),db=Depends(get_db)):
    row=s.owner(db,DailyPlan,id,user)
    current=s.active_plan(db,user,body.date)
    if row.local_date!=body.date or not current or current.id!=id: fail(409,'所选计划已不是当前版本')
    proposal=s.create_proposal(db,user,body.date,body.revision,body.meal,body.food_id,body.replace_food_id)
    db.commit();return s.proposal_dict(db,proposal)

@app.post(PREFIX+'/adjustments/propose')
def adjust(body: Replacement,user=Depends(auth),db=Depends(get_db)):
    proposal=s.create_proposal(db,user,body.date,body.revision,body.meal,body.food_id,body.replace_food_id)
    db.commit();return s.proposal_dict(db,proposal)

@app.get(PREFIX+'/adjustments')
def proposals(date: date,user=Depends(auth),db=Depends(get_db)):
    return [s.proposal_dict(db,p) for p in db.scalars(select(AdjustmentProposal).where(AdjustmentProposal.user_id==user.id,AdjustmentProposal.local_date==date,AdjustmentProposal.status=='pending',AdjustmentProposal.batch_id.is_(None)).order_by(AdjustmentProposal.id.desc()).limit(20))]

@app.post(PREFIX+'/adjustments/{id}/confirm')
def confirm(id: int,user=Depends(auth),db=Depends(get_db)):
    row=s.owner(db,AdjustmentProposal,id,user)
    if row.batch_id:fail(409,'多日草案请在聊天中整组确认，避免部分生效')
    result=s.confirm_proposal(db,user,row);db.commit();return result

@app.post(PREFIX+'/adjustments/{id}/reject')
def reject(id: int,user=Depends(auth),db=Depends(get_db)):
    proposal=s.owner(db,AdjustmentProposal,id,user)
    if proposal.batch_id:fail(409,'多日草案请整组拒绝')
    if proposal.status=='confirmed': fail(409,'已确认草案不可拒绝')
    if proposal.status=='rejected': return {'ok':True}
    s.bump(db,user,user.revision)
    db.refresh(proposal)
    if proposal.status=='confirmed': fail(409,'草案已在另一请求中确认，请刷新')
    proposal.status='rejected';db.commit();return {'ok':True}

@app.get(PREFIX+'/food-logs')
def get_logs(date: date,user=Depends(auth),db=Depends(get_db)):
    return s.logs(db,user,date)

@app.get(PREFIX+'/food-logs/{id}')
def get_log(id:int,user=Depends(auth),db=Depends(get_db)):
    return s.log_dict(db,s.owner(db,FoodLog,id,user))

def write_log(db,user,body,row=None):
    s.bump(db,user,body.revision)
    if body.status=='confirmed' and (body.finished=='unknown' or any(i.grams is None for i in body.items)):
        fail(422,'确认前请填写实际吃下克数以及是否吃完')
    p=s.profile_data(db,user)
    previous = s.log_dict(db,row)['items'] if row else []
    fields=dict(local_date=body.eaten_at.astimezone(ZoneInfo(p['timezone'])).date(),eaten_at=body.eaten_at.astimezone(timezone.utc),meal=body.meal,status=body.status,finished=body.finished,note=body.note)
    if row:
        for k,v in fields.items(): setattr(row,k,v)
        db.execute(delete(FoodLogItem).where(FoodLogItem.log_id==row.id,FoodLogItem.user_id==user.id))
    else:
        row=FoodLog(user_id=user.id,**fields);db.add(row);db.flush()
    for i in body.items:
        prior=next((x for x in previous if x['food_id']==i.food_id and x['grams']==i.grams and (i.food_id is not None or x['name']==i.name)),None)
        if i.food_id:
            food=db.get(Food,i.food_id)
            if not food: fail(422,'食物不存在')
            snap=s.snapshot(food,i.grams)
        else:
            if not i.name.strip(): fail(422,'自定义食物请填写名称')
            snap=dict(food_id=None,name=i.name,grams=i.grams,state='未知',group='自定义',nutrients={k:None for k in s.KEYS},source='用户描述，营养待完善',source_version='manual-1',demo=False,allergens=['未知'])
        db.add(FoodLogItem(user_id=user.id,log_id=row.id,snapshot=prior or snap))
    db.flush();result=s.log_dict(db,row);db.commit();return result

@app.post(PREFIX+'/food-logs')
def add_log(body: LogInput,user=Depends(auth),db=Depends(get_db)):
    return write_log(db,user,body)

@app.patch(PREFIX+'/food-logs/{id}')
def edit_log(id: int,body: LogInput,user=Depends(auth),db=Depends(get_db)):
    return write_log(db,user,body,s.owner(db,FoodLog,id,user))

@app.delete(PREFIX+'/food-logs/{id}')
def delete_log(id: int,revision: int,user=Depends(auth),db=Depends(get_db)):
    row=s.owner(db,FoodLog,id,user);s.bump(db,user,revision);db.delete(row);db.commit();return {'ok':True}

@app.get(PREFIX+'/daily-summary')
def daily_summary(date: date,user=Depends(auth),db=Depends(get_db)):
    return s.summary(db,user,date)

@app.post(PREFIX+'/feedback/generate')
def feedback(body: DateRequest,user=Depends(auth),db=Depends(get_db)):
    data=s.feedback_data(db,user,body.date)
    cached=db.scalar(select(Feedback).where(Feedback.user_id==user.id,Feedback.local_date==body.date,Feedback.revision==user.revision))
    if not cached: db.add(Feedback(user_id=user.id,local_date=body.date,revision=user.revision,data=data));db.commit()
    return data

@app.post(PREFIX+'/assistant/messages')
async def assistant(body: MessageInput,user=Depends(auth),db=Depends(get_db)):
    prior=db.scalar(select(ChatTurn).where(ChatTurn.user_id==user.id,ChatTurn.request_id==body.request_id))
    if prior:return chat_actions.serialize_turn(db,user,prior)['answer']
    result=await run_agent(db,user,body)
    if result.get('mode')=='consent_required':return result
    db.add(ChatTurn(user_id=user.id,local_date=body.date,question=body.message,answer=jsonable_encoder(result),request_id=body.request_id))
    db.commit()
    return result

@app.get(PREFIX+'/assistant/history')
def chat_history(user=Depends(auth),db=Depends(get_db)):
    return [chat_actions.serialize_turn(db,user,t) for t in chat_actions.recent_turns(db,user)]

@app.post(PREFIX+'/assistant/photos')
async def photo(body:PhotoInput,user=Depends(auth),db=Depends(get_db)):
    prior=db.scalar(select(ChatTurn).where(ChatTurn.user_id==user.id,ChatTurn.request_id==body.request_id))
    if prior:return chat_actions.serialize_turn(db,user,prior)['answer']
    result=await analyze_photo(db,user,body)
    local_date=body.eaten_at.astimezone(ZoneInfo(s.profile_data(db,user)['timezone'])).date()
    db.add(ChatTurn(user_id=user.id,local_date=local_date,question='[餐食照片] '+body.message,answer=jsonable_encoder(result),request_id=body.request_id))
    db.commit()
    return result

@app.post(PREFIX+'/assistant/batches/{batch_id}/confirm')
def confirm_chat_batch(batch_id:str,user=Depends(auth),db=Depends(get_db)):
    result=chat_actions.confirm_batch(db,user,batch_id);db.commit();return result

@app.post(PREFIX+'/assistant/batches/{batch_id}/reject')
def reject_chat_batch(batch_id:str,user=Depends(auth),db=Depends(get_db)):
    result=chat_actions.reject_batch(db,user,batch_id);db.commit();return result

@app.get(PREFIX+'/trends')
def trends(date: date,user=Depends(auth),db=Depends(get_db)):
    return [s.summary(db,user,date-timedelta(days=i)) for i in range(6,-1,-1)]

@app.get(PREFIX+'/weight-logs')
def weights(user=Depends(auth),db=Depends(get_db)):
    return [dict(id=w.id,date=w.local_date,kg=w.kg) for w in db.scalars(select(WeightLog).where(WeightLog.user_id==user.id).order_by(WeightLog.local_date.desc()).limit(100))]

@app.post(PREFIX+'/weight-logs')
def weight(body: WeightInput,user=Depends(auth),db=Depends(get_db)):
    s.bump(db,user,body.revision);db.add(WeightLog(user_id=user.id,local_date=body.date,kg=body.kg));db.commit();return {'ok':True}

@app.get(PREFIX+'/account/export')
def export(user=Depends(auth),db=Depends(get_db)):
    data={'account':{'email':user.email,'created_at':user.created_at},'format_version':1}
    for model in (Profile,NutritionTarget,DailyPlan,MealPlanItem,DailyState,FoodLog,FoodLogItem,AdjustmentProposal,Feedback,WeightLog,ChatTurn):
        data[model.__tablename__]=[{c.name:getattr(row,c.name) for c in inspect(model).columns} for row in db.scalars(select(model).where(model.user_id==user.id))]
    return Response(json.dumps(data,ensure_ascii=False,default=str,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="diet-export.json"'})

@app.delete(PREFIX+'/account')
def delete_account(request: Request,response: Response,revision: int,confirm: str,user=Depends(auth),db=Depends(get_db)):
    if confirm!='DELETE': fail(422,'请明确确认删除')
    s.bump(db,user,revision);db.delete(user);db.commit();response.delete_cookie(COOKIE,path='/');return {'ok':True}

DIST=Path(__file__).resolve().parents[2]/'frontend'/'dist'
if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
    @app.get('/{path:path}')
    def frontend(path: str):
        if path.startswith('api/'): fail(404,'接口不存在')
        return FileResponse(DIST/'index.html')
