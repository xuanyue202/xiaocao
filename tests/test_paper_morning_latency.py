"""Observe zero-effect morning paths without spending the price/model windows."""
import json
import sys

import pytest

from tests.test_paper_kol_integration import runtime, rows


def test_shadow_intelligence_does_not_hold_business_rendezvous(tmp_path, monkeypatch, capsys):
    from scripts import wait_for_agent_reviews as wait
    (tmp_path/'intelligence_review_queue_2026-11-13.json').write_text(json.dumps({
        'market_date':'2026-11-13', 'items':[{'code':'000001.XSHE'}]}))
    monkeypatch.setattr(sys, 'argv', ['wait', '--date', '2026-11-13', '--live-dir', str(tmp_path),
                                    '--intelligence-trade', 'shadow'])
    monkeypatch.setattr(wait.time, 'sleep', lambda *_:pytest.fail('Shadow is not an execution dependency'))
    wait.main()
    result = json.loads(capsys.readouterr().out)
    assert result['pending'] == 1 and result['reviewed'] == 0
    assert result['status'] == 'shadow_not_awaited'
    assert result['authority'] == 'shadow_only'


def test_all_cold_writer_seals_no_buy_without_price_wait(runtime, monkeypatch):
    from xiaocao.live import morning_bundle, paper_opening_high
    from xiaocao.live import paper_decision_support as support
    root, live, writer, run = runtime
    client = writer.XiaocaoClient()
    monkeypatch.setattr(writer, 'XiaocaoClient', lambda **kwargs: client)
    candidates = rows(live/'signal_snapshots.jsonl')
    for row in candidates:
        if row['book'] == 'B':
            row.update(mode_state='COLD', mode_trade_eligible=False, mode_exec_star=False)
    monkeypatch.setenv('CODEX_AUTOMATION_ID','xiaocao-daily-morning')
    monkeypatch.setenv('CODEX_THREAD_ID','producer')
    morning_bundle.publish_captured_batch(live, '2026-09-06',
        snapshot=''.join(json.dumps(r)+'\n' for r in candidates if r['book']=='B').encode(),
        strategy_sha='a'*40, source_readiness={'completeness':'observed_responses'}, timing={})
    monkeypatch.setenv('CODEX_AUTOMATION_ID','xiaocao-daily-morning-execution')
    monkeypatch.setenv('CODEX_THREAD_ID','original-consumer')
    monkeypatch.setenv('XIAOCAO_DAILY_RUN_DIR',str(root/'original-run'))
    monkeypatch.setattr(paper_opening_high,'capture_opening_high',
        lambda *a,**k:pytest.fail('No eligible order needs first-minute cost'))
    monkeypatch.setattr(writer,'_wait_until_fill_window_complete',
        lambda *a,**k:pytest.fail('No candidate must not wait'))
    parse=writer._parse_args
    def args():
        value=parse();value.no_wait_fill_window=False;value.allow_legacy_snapshots=False
        return value
    monkeypatch.setattr(writer,'_parse_args',args)
    before=(live/'paper_account.json').read_bytes()
    run()
    result=support.read_consumption_result(root,'2026-09-06','mode_exec_star')
    assert result['status']=='no_buy' and result['buy_count']==0
    assert (live/'paper_account.json').read_bytes()==before
