#!/usr/bin/env python3
from __future__ import annotations
import json, sys, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REQ=['README.md','docs/adr/ADR-0001-w2-product-and-ai-boundary.md','docs/product/W2_PRODUCT_CHARTER_V1.md','docs/product/W2_MARKET_SCOPE_V1.md','docs/product/W2_STATE_MODEL_V1.md','docs/product/W2_PREDICTION_TIMELINE_V1.md','docs/product/W2_ACCEPTANCE_METRICS_V1.md','docs/product/W2_PRODUCT_GLOSSARY_V1.md','docs/ai/W2_DEEPSEEK_ROLE_BOUNDARY_V1.md','docs/ai/W2_AI_RECOMMENDATION_INPUT_V1.md','docs/ai/W2_AI_RECOMMENDATION_OUTPUT_V1.md','docs/ai/W2_AI_RECOMMENDATION_VALIDATION_V1.md','docs/ai/W2_AI_RECOMMENDATION_CARD_V1.md','contracts/w2_product_policy.v1.json','contracts/w2_state_machine.v1.json','contracts/w2_metric_catalog.v1.json','contracts/ai_recommendation_input.v1.schema.json','contracts/ai_recommendation_output.v1.schema.json','contracts/ai_recommendation_card.v1.schema.json','examples/recommend/input.json','examples/recommend/ai_output.json','examples/recommend/card.json','examples/watch/input.json','examples/watch/ai_output.json','examples/watch/card.json','examples/skip/input.json','examples/skip/ai_output.json','examples/skip/card.json','scripts/check_w2_stage1_contracts.py','scripts/render_ai_card_text.py']
FORBIDDEN=['稳赢','稳赚','必中','必胜','保证命中','百分百','无风险','梭哈','重注','满仓','内幕','庄家送分']
def fail(m): print('W2 Stage1 contract check FAIL:',m,file=sys.stderr); sys.exit(1)
def load(p): return json.loads((ROOT/p).read_text(encoding='utf-8'))
def walk(v):
    if isinstance(v,dict):
        for x in v.values(): yield from walk(x)
    elif isinstance(v,list):
        for x in v: yield from walk(x)
    else: yield v
before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in REQ if (ROOT/p).is_file()}
for p in REQ:
    if not (ROOT/p).is_file(): fail('missing '+p)
for p in ['contracts/w2_product_policy.v1.json','contracts/w2_state_machine.v1.json','contracts/w2_metric_catalog.v1.json','contracts/ai_recommendation_input.v1.schema.json','contracts/ai_recommendation_output.v1.schema.json','contracts/ai_recommendation_card.v1.schema.json']:
    load(p)
for p in ['contracts/ai_recommendation_input.v1.schema.json','contracts/ai_recommendation_output.v1.schema.json','contracts/ai_recommendation_card.v1.schema.json']:
    if load(p).get('$schema')!='https://json-schema.org/draft/2020-12/schema': fail('schema draft mismatch '+p)
policy=load('contracts/w2_product_policy.v1.json')
if policy['current_project_gate']!='GATE_0_LEGACY' or policy['real_recommendation_enabled'] or policy['production_publish_enabled']: fail('gate/publish flags wrong')
if policy['supported_markets_phase_1']!=['ONE_X_TWO','ASIAN_HANDICAP','TOTALS']: fail('phase1 markets wrong')
if 'BTTS' in policy['supported_markets_phase_1'] or 'EXACT_SCORE' not in policy['explanatory_only_markets']: fail('market scope wrong')
if 'LOCKED' in policy['decision_statuses'] or 'SETTLED' in policy['decision_statuses']: fail('lifecycle leaked into decision')
for kind in ['recommend','watch','skip']:
    inp=load(f'examples/{kind}/input.json'); out=load(f'examples/{kind}/ai_output.json'); card=load(f'examples/{kind}/card.json')
    cands={c['candidate_id']:c for c in inp['legal_candidates']}; ev={e['evidence_id'] for e in inp['evidence_catalog']}; inv={i['condition_id'] for i in inp['invalidation_catalog']}; sc={s['score_id'] for s in inp['reference_score_catalog']}
    if inp['execution_mode']!='CONTRACT_EXAMPLE' or not inp['fixture']['synthetic_fixture'] or not inp['fixture']['not_a_real_recommendation']: fail(kind+' flags wrong')
    if len([card.get('primary_recommendation')] if card.get('primary_recommendation') else [])>1: fail('too many primary')
    if len([card.get('watched_candidate')] if card.get('watched_candidate') else [])>1: fail('too many watched')
    if len(card['reference_scenarios'])>2: fail('too many scores')
    sid=out.get('selected_candidate_id')
    if sid and sid not in cands: fail(kind+' selected candidate missing')
    for r in out.get('supporting_reasons',[]):
        if not set(r.get('evidence_refs',[])) <= ev: fail(kind+' bad support evidence')
    for r in out.get('counter_arguments',[]):
        if not set(r.get('evidence_refs',[])) <= ev: fail(kind+' bad counter evidence')
    for r in out.get('rejected_alternatives',[]):
        if r.get('candidate_id')==sid or r.get('candidate_id') not in cands: fail(kind+' bad rejected alternative')
    if not set(out.get('invalidation_condition_ids',[])) <= inv: fail(kind+' bad invalidation')
    for score_id in [out.get('main_reference_score_id'),out.get('alternative_reference_score_id')]:
        if score_id and score_id not in sc: fail(kind+' bad score id')
    if kind=='recommend':
        if card['statuses']!={'decision':'RECOMMEND','lifecycle':'LOCKED','data':'READY'}: fail('recommend statuses wrong')
        if cands[sid]['eligibility']!='ELIGIBLE': fail('recommend not eligible')
    if kind=='watch':
        if card.get('primary_recommendation') is not None or not card.get('watched_candidate') or card['watched_candidate']['official'] is not False: fail('watch recommendation wrong')
        if cands[sid]['eligibility']=='BLOCKED': fail('watch selected blocked')
    if kind=='skip':
        if out.get('selected_candidate_id') is not None or card.get('primary_recommendation') is not None or card.get('watched_candidate') is not None: fail('skip has recommendation')
        if inp['data_quality']['status']!='BLOCKED' or inp['hard_rules']['can_recommend'] is not False: fail('skip blocked flags wrong')
    for bad in ['odds','line','probability','scoreline']:
        if bad in out: fail(kind+' AI output raw numeric field '+bad)
    text=' '.join(str(x) for x in walk(out) if isinstance(x,str))
    if any(b in text for b in FORBIDDEN): fail(kind+' forbidden term')
readme=(ROOT/'README.md').read_text(encoding='utf-8')
if 'Stage 1 Product Contract' not in readme or 'does not have real recommendation capability' not in readme: fail('README boundary missing')
if any(x in readme for x in ['已完成 AI 推荐系统','已完成模型','已上线','已可正式推荐']): fail('README overclaims')
for p in ['contracts/w2_product_policy.v1.json','contracts/w2_state_machine.v1.json']:
    if '/Users/liudehua/.openclaw/workspace/w1_world_cup_engine' in (ROOT/p).read_text(encoding='utf-8'): fail('W1 path in runtime config')
after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in REQ if (ROOT/p).is_file()}
if before!=after: fail('checker modified files')
print('W2 Stage1 contract check PASS')
