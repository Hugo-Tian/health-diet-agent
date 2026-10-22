from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from .models import AdjustmentProposal,ChatTurn,FoodLog
from .security import fail
from . import services as s

def batch_rows(db,user,batch_id):
    rows=list(db.scalars(select(AdjustmentProposal).where(AdjustmentProposal.user_id==user.id,AdjustmentProposal.batch_id==batch_id).order_by(AdjustmentProposal.local_date)))
    if not rows: fail(404,'未找到这组计划草案')
    return rows

def batch_dict(db,rows):
    return {'batch_id':rows[0].batch_id,'status':rows[0].status,'proposals':[s.proposal_dict(db,p) for p in rows], 'requires_confirmation':rows[0].status=='pending'}

def propose_days(db,user,days):
    today=s.local_today(s.profile_data(db,user))
    if not 1<=len(days)<=7: fail(422,'每次可安排1至7天')
    dates=[d.date for d in days]
    if len(set(dates))!=len(dates): fail(422,'同一天不能重复安排')
    if any(d<today or d>today+timedelta(days=14) for d in dates): fail(422,'聊天调整仅支持今天至未来14天内的计划')
    batch_id=str(uuid4());rows=[]
    for day in sorted(days,key=lambda d:d.date):
        proposal=s.candidate_proposal(db,user,day.date,day.items) if day.items else s.create_proposal(db,user,day.date,user.revision)
        proposal.batch_id=batch_id
        proposal.reason='恢复规律进餐的多日安排，不因近期吃多而补偿性限食。'+proposal.reason
        rows.append(proposal)
    db.flush()
    return batch_dict(db,rows)

def confirm_batch(db,user,batch_id):
    rows=batch_rows(db,user,batch_id)
    if all(r.status=='confirmed' for r in rows): return batch_dict(db,rows)
    if any(r.status!='pending' for r in rows): fail(409,'这组草案状态已变化，请刷新')
    revision=rows[0].base_data_revision
    if any(r.base_data_revision!=revision for r in rows): fail(409,'草案依据不一致，请重新生成')
    s.bump(db,user,revision)
    for row in rows:
        db.refresh(row)
        if row.status!='pending': fail(409,'草案已在其他页面处理')
        s.confirm_proposal(db,user,row,revision_locked=True)
    return batch_dict(db,rows)

def reject_batch(db,user,batch_id):
    rows=batch_rows(db,user,batch_id)
    if all(r.status=='rejected' for r in rows):return batch_dict(db,rows)
    if any(r.status=='confirmed' for r in rows):fail(409,'已确认的整组计划不能拒绝')
    s.bump(db,user,user.revision)
    for row in rows:
        db.refresh(row)
        if row.status=='confirmed':fail(409,'草案已在其他页面确认')
        row.status='rejected'
    return batch_dict(db,rows)

def recent_turns(db,user,limit=30):
    return list(reversed(db.scalars(select(ChatTurn).where(ChatTurn.user_id==user.id).order_by(ChatTurn.id.desc()).limit(limit)).all()))

def serialize_turn(db,user,turn):
    result={'id':turn.id,'date':turn.local_date,'question':turn.question,'answer':turn.answer,'created_at':turn.created_at}
    batches=[]
    for b in turn.answer.get('batches',[]):
        batches.append(batch_dict(db,batch_rows(db,user,b['batch_id'])))
    proposals=[]
    for p in turn.answer.get('proposals',[]):
        row=db.scalar(select(AdjustmentProposal).where(AdjustmentProposal.id==p['id'],AdjustmentProposal.user_id==user.id))
        if row:proposals.append(s.proposal_dict(db,row))
    result['answer']={**turn.answer,'batches':batches,'proposals':proposals}
    if turn.answer.get('photo_log_id'):
        log=db.scalar(select(FoodLog).where(FoodLog.id==turn.answer['photo_log_id'],FoodLog.user_id==user.id))
        result['answer']['photo_status']=log.status if log else 'deleted'
    return result
