from pathlib import Path
import json
from xiaocao.live.morning_observability import review_notice, review_brief, terminal_notice


def test_full_evidence_is_referenced_not_injected_into_operator_messages():
    request = {'request_id': 'a'*64, 'request_sha256': 'a'*64,
        'requested_at': '2026-09-17T09:25:00+08:00',
        'entry_deadline': '2026-09-17T11:30:00+08:00', 'max_wait_seconds': 120,
        'candidates': [{'code': str(i), 'mode': 'N字低吸', 'mode_exec_star': i == 0,
            'mode_state': 'ACTIVE', 'market_price': 10, 'basket_price': 11,
            'unrelated_payload': 'x'*50000} for i in range(10)]}
    notice = review_notice(request, Path('full.json'), Path('receipt.json'), Path('brief.json'))
    assert len(json.dumps(notice)) < 2048
    assert 'candidates' not in notice and 'request' not in notice
    brief = review_brief(request)
    assert len(brief['candidates']) == 10
    assert brief['candidates'][0]['market_price'] == 10
    assert brief['review_deadline'] == '2026-09-17T09:27:00+08:00'
    assert request['candidates'][0]['unrelated_payload']  # immutable source untouched
    terminal = terminal_notice({'execution_receipts': [{'state': 'filled',
        'broker_order_id': '123', 'filled_shares': 100, 'locator_proof': 'x'*50000}]}, Path('run.json'))
    assert terminal['orders'][0]['broker_order_id'] == '123'
    assert len(json.dumps(terminal)) < 2048
