"""Local lexical retrieval: BM25 + curated-question overlap, fused with RRF.

Method references (independent implementation): docs/rag-references.md.
This is not a dense embedding model and does not infer a diagnosis.
"""
import math
import re
import unicodedata
from collections import Counter

STOP = {'怎么','如何','什么','可以','需要','一下','帮我','饮食','建议','应该','是否'}

def normalize(text):
    return unicodedata.normalize('NFKC',text).lower()

def tokens(text):
    text=normalize(text)
    parts=re.findall(r'[a-z]+|[\u4e00-\u9fff]+',text)
    return [term for part in parts for term in
            ([part] if part.isascii() else [part[i:i+2] for i in range(len(part)-1)]) if term not in STOP]

def phrase_hit(phrase,query):
    phrase=normalize(phrase)
    if phrase.isascii():
        return bool(re.search(r'(?<![a-z])'+re.escape(phrase)+r'(?![a-z])',query))
    return phrase in query

def rank_chunks(query,rows,limit=6):
    query=normalize(query[:1000]);qt=set(tokens(query))
    if not qt:return []
    bags=[Counter(tokens(' '.join([r['title'],r['content'],*r['aliases'],*r.get('questions',[])]))) for r in rows]
    df=Counter(t for bag in bags for t in bag);avg=sum(sum(b.values()) for b in bags)/max(len(bags),1)
    candidates=[]
    for row,bag in zip(rows,bags):
        hits=[a for a in row['aliases'] if phrase_hit(a,query)]
        # Curated paraphrases are retrieval aids, not additional medical evidence.
        coverage=0.0
        for question in row.get('questions',[]):
            ts=set(tokens(question));overlap=len(qt&ts)
            if overlap>=3:coverage=max(coverage,overlap/max(len(ts),1))
        if not hits and coverage<0.6:continue
        score=0.0;length=sum(bag.values())
        for term in qt:
            freq=bag[term]
            if freq:
                idf=math.log(1+(len(rows)-df[term]+0.5)/(df[term]+0.5))
                score+=idf*freq*2.5/(freq+1.5*(0.25+0.75*length/max(avg,1)))
        candidates.append({'row':row,'bm25':score,'match':coverage+(1 if hits else 0),
                           'matched_by':'alias' if hits else 'curated_question'})
    ranks={}
    for key in ('bm25','match'):
        for rank,item in enumerate(sorted(candidates,key=lambda x:(-x[key],x['row']['id'])),1):
            ident=item['row']['id'];ranks[ident]=ranks.get(ident,0)+1/(60+rank)
    ranked=sorted(candidates,key=lambda x:(-ranks[x['row']['id']],x['row']['id']))
    # Reserve one result per matched topic before adding more from the same topic.
    first=[];rest=[];seen=set()
    for item in ranked:
        topic=item['row']['topic_key']
        (rest if topic in seen else first).append(item);seen.add(topic)
    return [(x['row'],{'method':'bm25_question_rrf','matched_by':x['matched_by'],
                      'score':round(ranks[x['row']['id']],6)}) for x in (first+rest)[:limit]]
