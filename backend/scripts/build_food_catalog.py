"""Rebuild the checked-in catalog from USDA's official SR Legacy JSON ZIP.
Run from project root: python backend/scripts/build_food_catalog.py work/nutrition/sr-legacy.zip
No nutrients are manually authored. Chinese names and constraint tags are local curation.
"""
import hashlib,json,sys,zipfile
from pathlib import Path

URL='https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_json_2018-04.zip'
EXPECTED_SHA='0fe8ae486a2c8eb42cb96413f058deb51863a46c8fb8eeb4b1fb45006dd338ef'
# id, precise Chinese description, food group, weighing state, allergen tags, diet tags
ROWS=[
 (169757,'白米饭（长粒、未强化、无盐）','主食','熟重',[],['vegan']),
 (168932,'白米饭（短粒、未强化）','主食','熟重',[],['vegan']),
 (169704,'糙米饭（长粒）','主食','熟重',[],['vegan']),
 (169711,'糯米饭（未强化）','主食','熟重',[],['vegan']),
 (169756,'白大米（长粒、未强化）','主食','生重',[],['vegan']),
 (169703,'糙米（长粒）','主食','生重',[],['vegan']),
 (168871,'熟小米','主食','熟重',[],['vegan']),
 (169702,'生小米','主食','生重',[],['vegan']),
 (168917,'熟藜麦','主食','熟重',[],['vegan']),
 (170686,'烘烤荞麦粒（水煮）','主食','熟重',['荞麦'],['vegan']),
 (173905,'燕麦粥（水煮、未强化、无盐）','主食','熟重',['麸质'],['vegan']),
 (173904,'燕麦片（干、未强化）','主食','生重',['麸质'],['vegan']),
 (168484,'红薯（水煮、去皮）','主食','熟重',[],['vegan']),
 (168483,'红薯（带皮烤制、仅果肉、无盐）','主食','熟重',[],['vegan']),
 (168482,'红薯（生）','主食','生重',[],['vegan']),
 (170440,'土豆（水煮、去皮、无盐）','主食','熟重',[],['vegan']),
 (169999,'黄甜玉米（水煮、沥干、无盐）','主食','熟重',[],['vegan']),
 (168907,'日式荞麦面（煮熟）','主食','熟重',['麸质','荞麦'],['vegan']),
 (168909,'日式素面（煮熟）','主食','熟重',['麸质'],['vegan']),
 (168926,'鸡蛋面（煮熟、未强化、无盐）','主食','熟重',['麸质','蛋'],['vegetarian']),
 (172688,'全麦面包（商业配方，成分待核对）','主食','即食',['麸质','未知'],['unknown']),
 (171477,'鸡胸肉（去皮、烤制）','蛋白','熟重',[],['meat']),
 (170641,'牛里脊（去可见脂肪、烤制）','蛋白','熟重',[],['meat']),
 (175177,'罗非鱼（干热烹调）','蛋白','熟重',['鱼'],['meat']),
 (175168,'大西洋养殖三文鱼（干热烹调）','蛋白','熟重',['鱼'],['meat']),
 (175180,'虾（熟）','蛋白','熟重',['甲壳类'],['meat']),
 (173424,'鸡蛋（水煮、全熟）','蛋白','熟重',['蛋'],['vegetarian']),
 (172186,'鸡蛋（水波蛋）','蛋白','熟重',['蛋'],['vegetarian']),
 (171287,'鸡蛋（生）','蛋白','生重',['蛋'],['vegetarian']),
 (172475,'硬豆腐（生、硫酸钙凝固）','蛋白','生重',['大豆'],['vegan']),
 (172476,'普通豆腐（生、硫酸钙凝固）','蛋白','生重',['大豆'],['vegan']),
 (173757,'鹰嘴豆（水煮、无盐）','蛋白','熟重',[],['vegan']),
 (173728,'红小豆（水煮、无盐）','蛋白','熟重',[],['vegan']),
 (173735,'黑芸豆（水煮、无盐，非黑大豆）','蛋白','熟重',[],['vegan']),
 (175194,'红腰豆（水煮、无盐）','蛋白','熟重',[],['vegan']),
 (172421,'扁豆属小扁豆（水煮、无盐）','蛋白','熟重',[],['vegan']),
 (169283,'青大豆（水煮、沥干、无盐）','蛋白','熟重',['大豆'],['vegan']),
 (169967,'西兰花（水煮、沥干、无盐）','蔬菜','熟重',[],['vegan']),
 (170379,'西兰花（生）','蔬菜','生重',[],['vegan']),
 (168463,'菠菜（水煮、沥干、无盐）','蔬菜','熟重',[],['vegan']),
 (168462,'菠菜（生）','蔬菜','生重',[],['vegan']),
 (170394,'胡萝卜（水煮、沥干、无盐）','蔬菜','熟重',[],['vegan']),
 (170393,'胡萝卜（生）','蔬菜','生重',[],['vegan']),
 (169980,'大白菜（水煮、沥干、无盐）','蔬菜','熟重',[],['vegan']),
 (169979,'大白菜（生）','蔬菜','生重',[],['vegan']),
 (170391,'小白菜（水煮、沥干、无盐）','蔬菜','熟重',[],['vegan']),
 (169976,'卷心菜（水煮、沥干、无盐）','蔬菜','熟重',[],['vegan']),
 (168409,'黄瓜（带皮、生）','蔬菜','生重',[],['vegan']),
 (170457,'红番茄（成熟、生）','蔬菜','生重',[],['vegan']),
 (168437,'香菇（熟、无盐）','蔬菜','熟重',[],['vegan']),
 (169242,'香菇（鲜、生）','蔬菜','生重',[],['vegan']),
 (168436,'香菇（干）','蔬菜','生重',[],['vegan']),
 (168449,'南瓜（水煮、沥干、无盐）','蔬菜','熟重',[],['vegan']),
 (169292,'西葫芦（带皮、水煮、无盐）','蔬菜','熟重',[],['vegan']),
 (169229,'茄子（水煮、沥干、无盐）','蔬菜','熟重',[],['vegan']),
 (169988,'芹菜（生）','蔬菜','生重',['芹菜'],['vegan']),
 (169249,'绿叶生菜（生）','蔬菜','生重',[],['vegan']),
 (170108,'红甜椒（生）','蔬菜','生重',[],['vegan']),
 (170427,'绿甜椒（生）','蔬菜','生重',[],['vegan']),
 (171688,'苹果（带皮、生）','水果','生重',[],['vegan']),
 (173944,'香蕉（生、可食部）','水果','生重',[],['vegan']),
 (169097,'橙子（生、可食部）','水果','生重',[],['vegan']),
 (169118,'梨（生）','水果','生重',[],['vegan']),
 (174683,'红或绿葡萄（欧洲种、生）','水果','生重',[],['vegan']),
 (167762,'草莓（生）','水果','生重',[],['vegan']),
 (167765,'西瓜（生、可食部）','水果','生重',[],['vegan']),
 (168153,'绿心猕猴桃（生、可食部）','水果','生重',[],['vegan']),
 (171711,'蓝莓（生）','水果','生重',[],['vegan']),
 (172217,'全脂牛奶（脂肪3.25%、未强化）','乳豆','即食',['乳'],['vegetarian']),
 (172205,'低脂牛奶（脂肪2%、未强化）','乳豆','即食',['乳'],['vegetarian']),
 (171284,'原味全脂酸奶','乳豆','即食',['乳'],['vegetarian']),
 (173806,'花生（干烤、无盐）','坚果','即食',['花生'],['vegan']),
 (170187,'核桃仁（英国核桃）','坚果','即食',['坚果'],['vegan']),
 (170158,'巴旦木（干烤、无盐）','坚果','即食',['坚果'],['vegan']),
 (170162,'腰果（生）','坚果','生重',['坚果'],['vegan']),
 (170151,'芝麻（整粒、烘烤）','坚果','即食',['芝麻'],['vegan']),
 (171413,'橄榄油（食用）','油脂','即食',[],['vegan']),
 (171411,'大豆油（食用）','油脂','即食',['大豆'],['vegan']),
 (172336,'低芥酸菜籽油（食用）','油脂','即食',[],['vegan']),
]
NUTRIENTS={'kcal':(1008,'kcal'),'protein':(1003,'g'),'carbs':(1005,'g'),'fat':(1004,'g'),'fiber':(1079,'g'),'sodium_mg':(1093,'mg'),'calcium_mg':(1087,'mg'),'iron_mg':(1089,'mg'),'potassium_mg':(1092,'mg')}

def build(archive):
    raw=Path(archive).read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    if sha!=EXPECTED_SHA: raise ValueError('USDA archive changed: review before importing')
    with zipfile.ZipFile(archive) as z:
        data=json.loads(z.read(next(n for n in z.namelist() if n.endswith('.json'))))
    source={f['fdcId']:f for f in next(iter(data.values()))}
    result=[]
    for id,name,group,state,allergens,tags in ROWS:
        f=source[id]; nutrients={}; evidence={}
        for key,(nid,unit) in NUTRIENTS.items():
            values=[n for n in f['foodNutrients'] if n['nutrient']['id']==nid]
            if len(values)>1: raise ValueError('Duplicate nutrient')
            n=values[0] if values else None
            if n and n['nutrient']['unitName'].lower()!=unit.lower(): raise ValueError('Unexpected unit')
            nutrients[key]=n.get('amount') if n else None
            evidence[key]=n
        if any(nutrients[k] is None for k in ['kcal','protein','carbs','fat']): raise ValueError('Missing primary nutrient')
        portions=[{'unit':'100克可食部','grams':100.0,'source':'称重单位，不推定碗/杯容量'}]
        for p in f.get('foodPortions',[]):
            if not p.get('gramWeight') or not p.get('amount'):continue
            label=f"{p['amount']:g} {p.get('modifier') or p.get('measureUnit',{}).get('name','portion')}"
            if len(label)>40: continue
            portions.append({'unit':label,'grams':p['gramWeight'],'source':f'USDA FDC {id} 原始家用量；美国量具/规格'})
        provenance={'fdc_id':id,'ndb_number':f.get('ndbNumber'),'original_name':f['description'],'data_type':f['dataType'],'release':'2018-04','publication_date':f.get('publicationDate'),'retrieved_at':'2026-10-18','url':f'https://fdc.nal.usda.gov/food-details/{id}/nutrients','download_url':URL,'archive_sha256':sha,'license':'CC0-1.0','basis':'每100g可食部；按原条目生熟状态','nutrient_units':{k:v[1] for k,v in NUTRIENTS.items()},'carbohydrate_definition':'Carbohydrate, by difference（差减法，包含膳食纤维）；不等同中国标签的可利用碳水','mapping_note':'中文名称按原条目限定；美国食物参考，不能视为中国具体品种或餐馆菜品实测值','allergen_note':'本地根据食材名称保守标注，非 USDA 过敏认证；不保证无交叉接触','nutrient_evidence':evidence}
        result.append(dict(id=id,name=name,group=group,state=state,allergens=allergens,tags=tags,nutrients=nutrients,portions=portions,provenance=provenance))
    target=Path(__file__).resolve().parents[1]/'data'/'usda_catalog.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps({'version':'usda-sr-2018-v1','foods':result},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Built {len(result)} foods from official archive; no hand-entered nutrient values.')

if __name__=='__main__': build(sys.argv[1])
