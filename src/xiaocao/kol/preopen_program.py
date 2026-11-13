"""Budgeted source-owner preparation, separate from opening policy and effects."""
from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .publication import canonical_sha256
from . import opening_preparation as prep
from xiaocao.utils.atomic_files import atomic_write
from xiaocao.runner_recovery import _hash

OWNER = 'xiaocao-kol-hourly-low-bandwidth-operation'
TZ = ZoneInfo('Asia/Shanghai')


def clock() -> datetime:
    return datetime.now(TZ)


def seal(path: Path, value: dict) -> dict:
    body = {k:v for k,v in value.items() if k != 'sha256'}
    body['sha256'] = canonical_sha256(body)
    atomic_write(path, json.dumps(body,sort_keys=True).encode(),immutable=True)
    return body


def read(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError('KOL_PREOPEN_SYMLINK')
    value = json.loads(path.read_bytes())
    if not isinstance(value,dict):raise ValueError('KOL_PREOPEN_ARTIFACT_INVALID')
    if value.get('sha256') != canonical_sha256({k:v for k,v in value.items() if k!='sha256'}):
        raise ValueError('KOL_PREOPEN_ARTIFACT_ALTERED')
    return value


def owner(plan: dict) -> None:
    if (os.environ.get('CODEX_AUTOMATION_ID') != OWNER
            or os.environ.get('CODEX_THREAD_ID') != plan['owner_thread_id']):
        raise ValueError('KOL_PREOPEN_OWNER_MISMATCH')


def stage_for_input(inputs: dict) -> tuple[Path, dict, dict]:
    binding = inputs['binding']
    plan_path = Path(binding['preopen_program_path'])
    plan = read(plan_path)
    stage_path = Path(binding['preopen_stage_path'])
    if (not stage_path.resolve().is_relative_to((plan_path.parent/'stages').resolve())
            or binding['owner_thread_id'] != plan['owner_thread_id']
            or binding['automation_id'] != OWNER or binding['trade_date'] != plan['source_day']):
        raise ValueError('KOL_PREOPEN_STAGE_BINDING_INVALID')
    stage = read(stage_path)
    if (stage['plan_sha256'] != plan['sha256'] or stage['input_sha256'] != _hash(inputs)
            or inputs.get('intended_use_at') != stage.get('fresh_through')
            or stage.get('fresh_through') and stage['calendar_proof'].get('latest') != stage['fresh_through'][:10]):
        raise ValueError('KOL_PREOPEN_INPUT_CHANGED')
    return stage_path, stage, plan


def record_dispatch(input_path: Path, dispatch_path: Path, *, now: datetime) -> dict:
    inputs, _ = prep._inputs(input_path)
    stage_path, stage, plan = stage_for_input(inputs)
    owner(plan)
    dispatch = json.loads(dispatch_path.read_bytes())
    args, result = dispatch.get('tool_arguments',{}), dispatch.get('tool_result',{})
    if (dispatch.get('accepted') is not True or dispatch.get('binding') != inputs['binding']
            or dispatch.get('input_sha256') != _hash(inputs)
            or not dispatch.get('worker_id') or result.get('task_name') != dispatch['worker_id']
            or args.get('model') != 'gpt-6-sol' or args.get('reasoning_effort') != 'xhigh'
            or args.get('fork_turns') != 'none'
            or not (prep.aware(stage['opened_at']) <= prep.aware(dispatch['dispatched_at']) <= now
                    <= prep.aware(stage['dispatch_by']))):
        raise ValueError('KOL_PREOPEN_EARLY_DISPATCH_UNPROVEN')
    return seal(stage_path.with_name('dispatch.json'), {'stage_sha256':stage['sha256'],
        'input_sha256':stage['input_sha256'], 'dispatch_path':str(dispatch_path.resolve()),
        'dispatch_sha256':canonical_sha256(dispatch), 'worker_id':dispatch['worker_id'],
        'recorded_at':now.isoformat()})


def record_review(input_path: Path, context_path: Path, *, now: datetime) -> dict:
    inputs, _ = prep._inputs(input_path)
    stage_path, stage, plan = stage_for_input(inputs)
    owner(plan)
    dispatched = read(stage_path.with_name('dispatch.json'))
    context = json.loads(context_path.read_bytes())
    context_sha = canonical_sha256({k:v for k,v in context.items() if k!='context_sha256'})
    if (dispatched['stage_sha256'] != stage['sha256'] or dispatched['input_sha256'] != stage['input_sha256']
            or context.get('context_sha256') != context_sha or context.get('authority') != 0
            or prep.aware(context['as_of']) > now
            or not (prep.aware(dispatched['recorded_at']) <= now <= prep.aware(stage['review_open_by']))):
        raise ValueError('KOL_PREOPEN_REVIEW_NOT_STARTED_IN_TIME')
    return seal(stage_path.with_name('review-open.json'), {'stage_sha256':stage['sha256'],
        'input_sha256':stage['input_sha256'], 'reviewer_id':plan['owner_thread_id'],
        'context_sha256':context_sha, 'context_path':str(context_path.resolve()), 'opened_at':now.isoformat()})


def validate_acceptance(inputs: dict, draft: dict, review: dict, dispatch: dict,
                        context: dict, *, now: datetime) -> dict:
    stage_path, stage, plan = stage_for_input(inputs)
    dispatched = read(stage_path.with_name('dispatch.json'))
    opened = read(stage_path.with_name('review-open.json'))
    if (dispatched['stage_sha256'] != stage['sha256'] or opened['stage_sha256'] != stage['sha256']
            or dispatched['input_sha256'] != stage['input_sha256'] or opened['input_sha256'] != stage['input_sha256']
            or dispatched['dispatch_sha256'] != canonical_sha256(dispatch)
            or dispatched['worker_id'] != draft['worker_id']
            or opened['reviewer_id'] != review['reviewer_id']
            or opened['context_sha256'] != context['context_sha256']
            or prep.aware(draft['prepared_at']) > prep.aware(stage['review_open_by'])
            or not (prep.aware(opened['opened_at']) <= prep.aware(review['reviewed_at']) <= now
                    < prep.aware(stage['complete_by']) <= prep.aware(plan['complete_by']))):
        raise ValueError('KOL_PREOPEN_PREPARATION_OR_REVIEW_DEADLINE')
    return {'plan_sha256':plan['sha256'], 'stage_sha256':stage['sha256'],
        'dispatch_receipt_sha256':dispatched['sha256'], 'review_open_sha256':opened['sha256'],
        'completed_at':now.isoformat(), 'complete_by':stage['complete_by'], 'authority':0}


def complete(preparation_path: Path) -> dict:
    value = json.loads(preparation_path.read_bytes())
    inputs = json.loads(Path(value['input_path']).read_bytes())
    stage_path, stage, plan = stage_for_input(inputs)
    owner(plan)
    verified = prep.read_preparation(preparation_path,now=prep.aware(value['accepted_at']))
    if not verified.get('preopen_program'):
        raise ValueError('KOL_PREOPEN_ACCEPTANCE_UNPROVEN')
    return seal(stage_path.with_name('completed.json'), {'stage_sha256':stage['sha256'],
        'preparation_path':str(preparation_path.resolve()),'preparation_sha256':value['preparation_sha256'],
        'accepted_at':value['accepted_at'], 'preopen_program':verified['preopen_program']})


def create_plan(root: Path, *, acquired_at: datetime, slot: datetime, calendar: dict,
                runner_pid: int, thread_id: str) -> tuple[Path, dict]:
    if slot.hour not in {6,21} or not thread_id or '/' in thread_id or thread_id in {'.','..'}:
        raise ValueError('KOL_PREOPEN_SLOT_OR_OWNER_INVALID')
    day = acquired_at.astimezone(TZ).date()
    candidate = day if slot.hour == 6 else day+timedelta(days=1)
    trading = calendar.get('latest') == candidate.isoformat()
    target = candidate.isoformat() if trading else None
    deadline = (datetime.fromisoformat(str(day)+'T09:20:00+08:00') if slot.hour==6
                else acquired_at+timedelta(minutes=60))
    release = (datetime.fromisoformat(str(day)+'T07:30:00+08:00') if slot.hour==6 else acquired_at)
    value = {'schema_version':'kol-preopen-program.v1','authority':0,'automation_id':OWNER,
        'owner_thread_id':thread_id,'runner_pid':runner_pid,'source_day':str(day),
        'slot_start':slot.isoformat(),'acquired_at':acquired_at.isoformat(),
        'target_trade_date':target,'calendar_proof':calendar,
        'fresh_through':target+'T09:27:30+08:00' if target else None,
        'complete_by':deadline.isoformat(),'source_release_at':release.isoformat(),
        'dispatch_seconds':300,'synthesis_seconds':1800,'review_seconds':900,
        'readiness_target':'09:20','scope':'morning' if slot.hour==6 and (trading or not calendar.get('latest')) else 'source_only_or_evening'}
    directory=root/'output/live/kol_preopen_programs'/slot.strftime('%Y%m%dT%H00%z')/thread_id
    path=directory/'plan.json'
    if path.exists():
        existing=read(path)
        if existing != {**value,'sha256':canonical_sha256(value)}:
            raise ValueError('KOL_PREOPEN_ORIGINAL_PLAN_ALREADY_EXISTS')
        return path,existing
    return path,seal(path,value)


def source_release_admitted(slot: datetime, acquired_at: datetime | None, now: datetime) -> bool:
    raw=os.environ.get('XIAOCAO_KOL_PREOPEN_PLAN')
    if not raw or slot.hour != 6 or acquired_at is None:
        return False
    plan=read(Path(raw));owner(plan)
    release=read(Path(raw).with_name('source-release.json'))
    return (plan['runner_pid']==os.getpid() and plan['slot_start']==slot.isoformat()
        and plan['acquired_at']==acquired_at.isoformat()
        and release['plan_sha256']==plan['sha256']
        and plan['source_release_at']==slot.replace(hour=7,minute=30).isoformat()
        and prep.aware(release['released_at']).astimezone(TZ).date()==slot.astimezone(TZ).date()
        and prep.aware(plan['source_release_at']) <= prep.aware(release['released_at']) <= now)


class Program:
    """One local owner; models are dispatched by the agent via exact receipts."""
    def __init__(self, root: Path, path: Path, *, now=clock, sleep=time.sleep, emit=None,
                 input_builder=None, calendar_probe=None):
        self.root,self.path,self.plan=root,path,read(path)
        self.now,self.sleep=now,sleep
        self.emit=emit or (lambda row:print(json.dumps(row,ensure_ascii=False),flush=True))
        self.input_builder=input_builder or self._inputs
        self.calendar=dict(self.plan['calendar_proof'])
        self.target_trade_date=self.plan['target_trade_date']
        self.fresh_through=self.plan['fresh_through']
        self.calendar_retry_after=prep.aware(self.plan['acquired_at'])+timedelta(minutes=5)
        self.calendar_probe=calendar_probe or (lambda:probe_calendar(self.root,self.calendar['queried_date']))
        self._mutex=threading.RLock()
        self.current=None
        self.seen=set()
        self.stop=threading.Event()
        self.last_watch=None
        self.last_checkpoint=None
        self.last_refresh=None

    def event(self,name,**fields):
        key=canonical_sha256({'name':name,**fields})
        if key not in self.seen:
            self.seen.add(key)
            self.emit({'event':name,'program_path':str(self.path),'authority':0,**fields})

    def _inputs(self) -> dict:
        args=[sys.executable,str(self.root/'scripts/kol_trading_prepare.py'),'rolling-inputs',
              '--root',str(self.root),'--output-dir',str(self.path.parent/'inputs')]
        if self.fresh_through:
            args+=['--fresh-through',self.fresh_through]
        result=subprocess.run(args,cwd=self.root,text=True,capture_output=True,timeout=45)
        try:return json.loads(result.stdout.splitlines()[-1])
        except (ValueError,IndexError):return {'status':'blocked','reason':'KOL_PREOPEN_INPUT_COMMAND_FAILED'}

    def refresh(self) -> dict:
        with self._mutex:
            try:
                return self._refresh()
            except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as exc:
                reason=(str(exc) if str(exc).startswith('KOL_PREOPEN_') else
                        'KOL_PREOPEN_INPUT_TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else type(exc).__name__)
                self.current={**(self.current or {}),'status':'source_verification_failed',
                              'sources_current':False,'reason':reason}
                self.event('kol_preopen_program_fault',reason=reason)
                return self.status()

    def _refresh(self) -> dict:
        now=self.now()
        if now>=prep.aware(self.plan['complete_by']):return self.status()
        if not self.calendar.get('latest') and now>=self.calendar_retry_after:
            self.calendar_retry_after=now+timedelta(minutes=5)
            resolved=self.calendar_probe()
            if resolved.get('latest'):
                candidate=self.calendar.get('queried_date',self.plan['source_day'])
                self.calendar=seal(self.path.parent/('calendar-'+canonical_sha256(resolved)+'.json'),resolved)
                self.target_trade_date=candidate if resolved['latest']==candidate else None
                self.fresh_through=candidate+'T09:27:30+08:00' if self.target_trade_date else None
        result=(self.input_builder() if self.calendar.get('latest') else
                {'status':'blocked','reason':'KOL_PREOPEN_CALENDAR_UNPROVEN'})
        now=self.now()
        if now>=prep.aware(self.plan['complete_by']):
            self.current={**(self.current or {}),'status':'source_verification_late','sources_current':False}
            return self.status()
        previous=self.current
        if result['status']=='reused':
            self.current={'status':'reused','preparation_path':result['path'],
                          'preparation_sha256':result['preparation_sha256'],'sources_current':True,'observed_at':now.isoformat()}
            if previous and previous.get('stage_path') and Path(previous['stage_path']).with_name('dispatch.json').exists() and not worker_finished(Path(previous['stage_path'])):
                self.current={**previous,'status':'reused_waiting_owned_worker','sources_current':True}
        elif result['status']!='written':
            self.current={'status':'source_blocked','reason':result.get('reason','KOL_PREOPEN_SOURCE_UNPROVEN'),
                          'observed_at':now.isoformat(),'source_diagnostic':result}
            self.event('kol_preopen_source_blocked',reason=self.current['reason'],evidence_path=result.get('path'))
            if previous and previous.get('stage_path'):
                self.current={**previous,**self.current,'status':'source_blocked_worker_still_owned','sources_current':False}
        else:
            inputs=json.loads(Path(result['path']).read_bytes())
            if self.fresh_through and inputs.get('intended_use_at') != self.fresh_through:
                raise ValueError('KOL_PREOPEN_MORNING_HORIZON_UNPROVEN')
            projection=prep.read_projection(inputs['projection'])
            key=canonical_sha256({'units':prep.viewpoint_units(projection),'rules':inputs['rules'],
                                   'fresh_through':self.fresh_through})
            stage_path=self.path.parent/'stages'/key/'stage.json'
            previous=self.current
            if previous and previous.get('stage_path') and previous.get('key')!=key:
                old=Path(previous['stage_path'])
                if (old.with_name('dispatch.json').exists() and not worker_finished(old)):
                    self.current={**previous,'status':'source_changed_worker_still_owned','pending_key':key,'sources_current':False}
                    self.event('kol_preopen_source_changed',stage_path=str(old))
                    return self.status()
            if not stage_path.exists():
                end=min(now+timedelta(minutes=45),prep.aware(self.plan['complete_by']))
                remaining=(end-now).total_seconds()
                reserve=min(900,remaining/3)
                inputs['binding']={**inputs['binding'],'preopen_program_path':str(self.path),
                                   'preopen_stage_path':str(stage_path)}
                bound=prep.write_artifact(stage_path.parent,inputs,'.inputs.json')
                seal(stage_path,{'plan_sha256':self.plan['sha256'],'key':key,
                    'input_path':str(bound),'input_sha256':_hash(inputs),'opened_at':now.isoformat(),
                    'fresh_through':self.fresh_through,'calendar_proof':self.calendar,
                    'dispatch_by':min(now+timedelta(minutes=5),end,
                        prep.aware(self.plan['acquired_at'])+timedelta(minutes=5) if self.last_refresh is None else end).isoformat(),
                    'review_open_by':(end-timedelta(seconds=reserve)).isoformat(), 'complete_by':end.isoformat()})
            self.current={'status':'preparing','stage_path':str(stage_path),'key':key,'sources_current':True}
            stage=read(stage_path)
            if not stage_path.with_name('dispatch.json').exists():
                self.event('kol_preopen_dispatch_required',input_path=stage['input_path'],
                    stage_path=str(stage_path),dispatch_by=stage['dispatch_by'],
                    review_open_by=stage['review_open_by'],complete_by=stage['complete_by'])
        self.last_refresh=now
        return self.status()

    def status(self) -> dict:
        with self._mutex:
            try:
                return self._status()
            except (ValueError,OSError,KeyError,TypeError) as exc:
                result={**(self.current or {}),'status':'preparation_proof_unproven',
                    'sources_current':False,'reason':type(exc).__name__,'morning_ready':False,
                    'program_sha256':self.plan['sha256'],'observed_at':self.now().isoformat(),
                    'complete_by':self.plan['complete_by'],'target_trade_date':self.target_trade_date,
                    'policy_adoption':'not_performed'}
                self.current=result
                atomic_write(self.path.with_name('status.json'),json.dumps(result,sort_keys=True).encode())
                return result

    def _status(self) -> dict:
        result=dict(self.current or {'status':'not_started'})
        now=self.now()
        if result.get('stage_path'):
            path=Path(result['stage_path']);stage=read(path)
            done=path.with_name('completed.json')
            if done.exists() and result.get('sources_current') is True:
                proof=read_completed(path)
                result.update(status='accepted',preparation_path=proof['preparation_path'],
                              preparation_sha256=proof['preparation_sha256'])
            elif now>=prep.aware(stage['complete_by']):result['status']='missed_preparation_deadline'
            elif not path.with_name('dispatch.json').exists() and now>prep.aware(stage['dispatch_by']):
                result['status']='missed_dispatch_deadline'
            elif not path.with_name('review-open.json').exists() and now>=prep.aware(stage['review_open_by']):
                result['status']='missed_review_start'
            else:
                self.event('kol_preopen_review_required',input_path=stage['input_path'],
                           stage_path=str(path),complete_by=stage['complete_by'])
        if now>=prep.aware(self.plan['complete_by']) and result['status'] not in {'accepted','reused'}:
            result['status']='missed_readiness_deadline'
        result.update(program_sha256=self.plan['sha256'],observed_at=now.isoformat(),
                      complete_by=self.plan['complete_by'],target_trade_date=self.target_trade_date,
                      sources_verified_as_of=self.last_refresh.isoformat() if self.last_refresh else None,
                      policy_adoption='not_performed',
                      morning_ready=result['status'] in {'accepted','reused'} and self.target_trade_date is not None)
        atomic_write(self.path.with_name('status.json'),json.dumps(result,sort_keys=True).encode())
        return result

    def before_source(self):
        self.refresh()
        while self.now()<prep.aware(self.plan['source_release_at']):
            self.status();self.sleep(min(2,max(0,(prep.aware(self.plan['source_release_at'])-self.now()).total_seconds())))
        if self.now().astimezone(TZ).date().isoformat()!=self.plan['source_day']:
            raise ValueError('KOL_PREOPEN_SOURCE_RELEASE_DATE_EXPIRED')
        seal(self.path.with_name('source-release.json'),{'plan_sha256':self.plan['sha256'],
                                                       'released_at':self.now().isoformat()})

    def _watch(self):
        # Only complete local publication ledger changes or coarse checkpoints
        # trigger cache projection work; ordinary waits do not re-run models.
        while not self.stop.wait(2):
            try:
                stamp=self.now()
                if stamp>=prep.aware(self.plan['complete_by']):
                    self.event('kol_preopen_readiness_deadline',**self.status())
                    break
                ledger=self.root/'output/live/kol_daily/publications/events.jsonl'
                signature=(ledger.stat().st_mtime_ns,ledger.stat().st_size) if ledger.exists() else None
                done=Path(self.current['stage_path']).with_name('completed.json') if self.current and self.current.get('stage_path') else None
                terminal=done.with_name('worker-terminal.json') if done else None
                signature=(signature,done.stat().st_mtime_ns if done and done.exists() else None,
                           terminal.stat().st_mtime_ns if terminal and terminal.exists() else None)
                checkpoint_key=stamp.strftime('%Y-%m-%dT%H:%M')
                checkpoint=stamp.strftime('%H:%M') in {'08:30','09:00','09:10'} and checkpoint_key!=self.last_checkpoint
                changed=signature!=self.last_watch
                calendar_due=not self.calendar.get('latest') and stamp>=self.calendar_retry_after
                if stamp<prep.aware(self.plan['complete_by']) and (changed or checkpoint or calendar_due):
                    self.last_watch=signature
                    if checkpoint:self.last_checkpoint=checkpoint_key
                    self.refresh()
                self.status()
            except (ValueError,OSError,KeyError,subprocess.TimeoutExpired) as exc:
                with self._mutex:
                    self.current={**(self.current or {}),'status':'source_verification_failed','sources_current':False}
                self.event('kol_preopen_program_fault',reason=type(exc).__name__)

    def monitor(self):
        self.monitor_thread=threading.Thread(target=self._watch,daemon=True)
        self.monitor_thread.start()
        return self.monitor_thread

    def finish(self) -> dict:
        if getattr(self,'finished',False):return self.status()
        while self.now()<prep.aware(self.plan['complete_by']):
            status=self.status()
            if (self.plan['scope']!='morning' or self.calendar.get('latest') and not self.target_trade_date) and status['status'] in {'accepted','reused','source_blocked'}:break
            self.sleep(1)
        self.stop.set()
        if getattr(self,'monitor_thread',None):self.monitor_thread.join(timeout=46)
        status=self.status()
        self.event('kol_preopen_program_result',**status)
        self.finished=True
        return status


def probe_calendar(root: Path, day: str) -> dict:
    command=[sys.executable,'-m','xiaocao','--format','json','--timeout','8','--retries','0',
             'calendar','latest','--date',day]
    try:
        result=subprocess.run(command,cwd=root,text=True,capture_output=True,timeout=15)
        calendar=json.loads(result.stdout) if result.returncode==0 else {'status':'unproved'}
        if not isinstance(calendar,dict):calendar={'status':'unproved'}
    except (OSError,ValueError,subprocess.TimeoutExpired):calendar={'status':'unproved'}
    return {**calendar,'queried_date':day,'observed_at':clock().isoformat()}


def startup(root: Path) -> Program | None:
    """Run only in the opt-in fresh source owner, before mailbox/acquisition."""
    if os.environ.get('XIAOCAO_KOL_PREOPEN_ENABLED') != 'v1':return None
    if os.environ.get('CODEX_AUTOMATION_ID') != OWNER or not os.environ.get('CODEX_THREAD_ID'):
        raise ValueError('KOL_PREOPEN_OWNER_REQUIRED')
    slot=prep.aware(os.environ['XIAOCAO_AUTOMATION_HOUR_START_AT'])
    acquired=prep.aware(os.environ['XIAOCAO_AUTOMATION_ACQUIRED_AT'])
    from .automation_slot import validate_automation_slot
    validate_automation_slot(slot,acquired,clock())
    candidate=acquired.astimezone(TZ).date()+timedelta(days=1 if slot.hour==21 else 0)
    calendar=probe_calendar(root,str(candidate))
    path,plan=create_plan(root,acquired_at=acquired,slot=slot,calendar=calendar,
                           runner_pid=os.getpid(),thread_id=os.environ['CODEX_THREAD_ID'])
    os.environ['XIAOCAO_KOL_PREOPEN_PLAN']=str(path)
    program=Program(root,path)
    atexit.register(program.finish)
    program.event('kol_preopen_program_started',complete_by=plan['complete_by'],
                  source_release_at=plan['source_release_at'],synthesis_seconds=1800,review_seconds=900)
    program.monitor()
    program.before_source()
    return program


def record_worker_terminal(input_path: Path, receipt_path: Path, *, now: datetime) -> dict:
    """Release a finished model, never infer completion from a timeout/rejection."""
    inputs=prep.read_json(input_path)
    stage_path,stage,plan=stage_for_input(inputs);owner(plan)
    dispatched=read(stage_path.with_name('dispatch.json'))
    receipt=json.loads(receipt_path.read_bytes())
    agents=(receipt.get('tool_result') or {}).get('agents',[])
    matches=[row for row in agents if row.get('agent_name')==dispatched['worker_id']]
    status=matches[0].get('agent_status') if len(matches)==1 else None
    if (receipt.get('tool_name')!='collaboration.list_agents' or receipt.get('tool_arguments')!={}
            or not isinstance(status,dict) or set(status)!={'completed'}
            or not isinstance(status['completed'],str)
            or not (prep.aware(dispatched['recorded_at'])<=prep.aware(receipt['observed_at'])<=now)):
        raise ValueError('KOL_PREOPEN_WORKER_TERMINAL_UNPROVEN')
    return seal(stage_path.with_name('worker-terminal.json'),{'stage_sha256':stage['sha256'],
        'worker_id':dispatched['worker_id'],'receipt_path':str(receipt_path.resolve()),
        'receipt_sha256':canonical_sha256(receipt),'observed_at':receipt['observed_at']})


def read_completed(stage_path: Path) -> dict:
    stage=read(stage_path)
    proof=read(stage_path.with_name('completed.json'))
    prepared=prep.read_json(Path(proof['preparation_path']))
    dispatched=read(stage_path.with_name('dispatch.json'))
    if (proof['stage_sha256']!=stage['sha256']
            or proof['preparation_sha256']!=prepared.get('preparation_sha256')
            or prepared.get('preparation_sha256')!=canonical_sha256({k:v for k,v in prepared.items() if k!='preparation_sha256'})
            or prepared.get('input_sha256')!=stage['input_sha256']
            or prepared.get('worker_id')!=dispatched['worker_id']
            or prepared.get('preopen_program')!=proof.get('preopen_program')
            or (prepared.get('preopen_program') or {}).get('stage_sha256')!=stage['sha256']):
        raise ValueError('KOL_PREOPEN_WORKER_COMPLETION_UNPROVEN')
    return proof


def worker_finished(stage_path: Path) -> bool:
    if stage_path.with_name('completed.json').exists():
        read_completed(stage_path)
        return True
    terminal=stage_path.with_name('worker-terminal.json')
    if not terminal.exists():return False
    stage=read(stage_path);proof=read(terminal)
    dispatched=read(stage_path.with_name('dispatch.json'))
    receipt=prep.read_json(Path(proof['receipt_path']))
    matches=[row for row in (receipt.get('tool_result') or {}).get('agents',[])
             if row.get('agent_name')==dispatched['worker_id']]
    state=matches[0].get('agent_status') if len(matches)==1 else None
    if (proof['stage_sha256']!=stage['sha256'] or proof['worker_id']!=dispatched['worker_id']
            or proof['receipt_sha256']!=canonical_sha256(receipt)
            or receipt.get('tool_name')!='collaboration.list_agents' or receipt.get('tool_arguments')!={}
            or not isinstance(state,dict) or set(state)!={'completed'}
            or not isinstance(state['completed'],str)):
        raise ValueError('KOL_PREOPEN_WORKER_TERMINAL_UNPROVEN')
    return True
