"""Replay exact archived API observations without a client or network fallback."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from xiaocao.datasource.api_source import ApiDataSource
from xiaocao.strategy import run_strategy
from xiaocao.strategy.mode_switch import select_executable_candidates


class ArchivedSource(ApiDataSource):
    def __init__(self, observations: list[dict]):
        super().__init__(SimpleNamespace(cache=None), resolve_security_universe=any(
            row['source']=='security_directory' for row in observations))
        self.archived = observations
        self.position = 0
        self._observe_enabled = True

    def _observe(self, kind, date, fetch, *, requested_codes=None, cache_key=()):
        if self.position >= len(self.archived):
            raise ValueError('RAW_REPLAY_UNRECORDED_SOURCE:'+kind)
        observation = self.archived[self.position]
        if (observation['source']!=kind or observation['requested_date']!=date
                or list(requested_codes or [])!=observation.get('requested_codes',[])):
            raise ValueError('RAW_REPLAY_SOURCE_SEQUENCE_MISMATCH:'+kind)
        path = Path(observation['response_path'])
        if path.is_symlink():
            raise ValueError('RAW_REPLAY_SOURCE_SYMLINK')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=observation['response_sha256']:
            raise ValueError('RAW_REPLAY_SOURCE_HASH_MISMATCH')
        self.position += 1
        self.observations.append(copy.deepcopy(observation))
        return json.loads(raw)


def raw_strategy(checkpoint: dict, original_rows: list[dict]) -> tuple[list[dict], dict]:
    """Recompute actual raw signals and baseline ranks with recorded prewake inputs.

    Mode qualifications, K/P scores and price facts are taken from this exact
    archived batch. Model training/inference and fresh market/source authority
    are outside this replay. The strategy reads only bound API response files.
    """
    observations = checkpoint['capture']['source_readiness']['sources']
    source = ArchivedSource(observations)
    date = checkpoint['binding']['market_date']
    signals = run_strategy(date,source,profile='validated_v5',adaptive_modes=False)
    active = [row for row in signals if row.get('adaptive_active') in (True,None)]
    identities = {(row['code'],row['mode']) for row in active}
    expected = {(row['code'],row['mode']) for row in original_rows}
    if identities!=expected or source.position!=len(observations):
        raise ValueError('RAW_REPLAY_SIGNAL_UNIVERSE_OR_COVERAGE_MISMATCH')
    baseline = select_executable_candidates(copy.deepcopy(original_rows),top_n=3)
    selected = [(row['code'],row['mode']) for row in baseline if row.get('mode_exec_star') is True]
    original_selected = [(row['code'],row['mode']) for row in original_rows if row.get('mode_exec_star') is True]
    if selected!=original_selected:
        raise ValueError('RAW_REPLAY_BASELINE_RANK_MISMATCH')
    return baseline, {'status':'replayed','source_count':source.position,'signal_count':len(signals),
        'active_count':len(active),'baseline_selection_parity':True,
        'prewake_inputs':'recorded_mode_qualifications_KP_scores_and_price_facts',
        'optional_state_vector':'not_recomputed_recorded_candidate_features_retained',
        'query_binding':'recorded_kind_date_code_sequence_and_response_hash; cache_key_not_archived',
        'network_calls':0}
