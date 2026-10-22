"""Versioned target policy. No unverified BMR/TDEE formula is shipped."""
from .security import fail

VERSION='manual-1'
METHOD='用户手动设定'
SOURCE='用户提供；未经专业核验'

def manual_target(body, restricted: bool):
    if restricted:
        fail(422,'当前服务范围不支持热量限制目标，请保留记录并咨询专业人员。')
    if body.lower > body.upper:
        fail(422,'目标下限不能超过上限')
    return dict(lower=body.lower,upper=body.upper,unit='kcal/日',method=METHOD,source=SOURCE,version=VERSION,assumptions=['不使用体重或活动公式推断目标','此区间不是健康处方；输入范围仅是应用校验范围，不表示安全阈值'])
