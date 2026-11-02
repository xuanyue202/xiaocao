"""Archived source replay must never substitute fresh network or altered bytes."""
import hashlib
import json
import pytest
from xiaocao.kol.replay_inputs import ArchivedSource


def test_exact_archived_source_reads_once_and_rejects_tamper_or_other_query(tmp_path):
    raw=json.dumps([{'code':'000001.XSHE'}]).encode()
    path=tmp_path/'source.json';path.write_bytes(raw)
    observation={'source':'stock_index','requested_date':'2026-11-02','requested_codes':['000001.XSHE'],
        'response_path':str(path),'response_sha256':hashlib.sha256(raw).hexdigest()}
    def forbidden():raise AssertionError('offline network fallback forbidden')
    source=ArchivedSource([observation])
    assert source._observe('stock_index','2026-11-02',forbidden,requested_codes=['000001.XSHE'])==[{'code':'000001.XSHE'}]
    with pytest.raises(ValueError,match='UNRECORDED_SOURCE'):
        source._observe('stock_index','2026-11-02',forbidden,requested_codes=['000001.XSHE'])
    source=ArchivedSource([observation])
    with pytest.raises(ValueError,match='SEQUENCE_MISMATCH'):
        source._observe('stock_index','2026-11-02',forbidden,requested_codes=['000002.XSHE'])
    path.write_bytes(b'[]')
    with pytest.raises(ValueError,match='HASH_MISMATCH'):
        source._observe('stock_index','2026-11-02',forbidden,requested_codes=['000001.XSHE'])
