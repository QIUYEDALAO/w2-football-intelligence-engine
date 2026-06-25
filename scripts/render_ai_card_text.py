#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path

def main():
    if len(sys.argv)!=2:
        print('usage: render_ai_card_text.py <card.json>', file=sys.stderr); return 2
    card=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    f=card['fixture']; st=card['statuses']; ai=card['ai_analysis']
    print(f"{f['competition_name_cn']} · {f['stage']}    W2 Research Review · {card['analysis_context']['analysis_phase']}")
    print(f"{f['home_team']['name_cn']} VS {f['away_team']['name_cn']}    开赛 {f['kickoff_utc']}")
    print(f"[{st['decision']}] [grade {card['display_grade']}] [data {st['data']}] [lifecycle {st['lifecycle']}]")
    if st['decision']=='RECOMMEND':
        r=card['primary_recommendation']
        print(f"AI最终推荐: {r['market']} {r['selection']} line={r['line']} odds={r['current_decimal_odds']} official={r['official']}")
    elif st['decision']=='WATCH':
        r=card['watched_candidate']
        print(f"尚未形成正式推荐: 观察 {r['market']} {r['selection']} official={r['official']}")
    else:
        print('SKIP: 不显示任何正式推荐方向')
    print('AI一句话结论:', ai['headline_cn'])
    print('AI比赛判断:', ai['match_read_cn'])
    print('AI盘口理解:', ai['market_read_cn'])
    print('参考剧情:', ' / '.join(f"{s['role']} {s['scoreline']}" for s in card['reference_scenarios']) or '无')
    print('风险:', '; '.join(a['text_cn'] for a in card['counter_arguments']) or '无')
    print('改变观点条件:', '; '.join(i['display_text_cn'] for i in card['invalidation_conditions']) or '无')
    return 0
if __name__=='__main__': raise SystemExit(main())
