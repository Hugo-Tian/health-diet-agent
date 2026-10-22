"""Run from backend: python -m app.evaluate_rag. No API calls/user records.

This curated regression set is not an independent clinical benchmark.
"""
import json
from pathlib import Path
from .knowledge import corpus,search_guidance

def evaluate():
    cases=json.loads((Path(__file__).resolve().parents[1]/'data'/'rag_eval.json').read_text(encoding='utf-8'))
    rows=[];hits=total=negative_ok=negative_total=0
    for case in cases:
        found=search_guidance(case['query'])['sources'];ids={r['id'] for r in found};expected=set(case['expected'])
        bad=any(r['topic_key'] in case.get('forbidden_topics',[]) for r in found)
        if expected: hits+=len(expected&ids);total+=len(expected)
        else: negative_total+=1;negative_ok+=not ids
        passed=expected.issubset(ids) and not bad if expected else not ids
        rows.append({'query':case['query'],'expected':sorted(expected),'retrieved':sorted(ids),'passed':passed})
    return {'version':corpus()['version'],'method':'bm25_question_rrf','cases':len(cases),
            'passed':sum(r['passed'] for r in rows),'recall_at_6':round(hits/max(total,1),4),
            'negative_rejection_rate':round(negative_ok/max(negative_total,1),4),'results':rows}

if __name__=='__main__':
    result=evaluate();print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['passed']==result['cases'] else 1)
