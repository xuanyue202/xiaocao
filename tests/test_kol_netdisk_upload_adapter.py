import json
from pathlib import Path
import shutil
import subprocess
import pytest


def test_inspection_counts_rows_from_every_upload_panel():
    adapter = Path(__file__).parents[1] / "opencli/clis/baidu-netdisk/upload.js"
    script = r"""
const fs = require('fs'), vm = require('vm');
let spec;
const sandbox = {process, URL, URLSearchParams, cli:value=>spec=value,
  Strategy:{UI:'UI'}, ArgumentError:Error, AuthRequiredError:Error, CommandExecutionError:Error};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8').replace(/import[\s\S]*?from '[^']+';/g,''),sandbox);
const url='https://pan.baidu.com/disk/main#/index?path='+encodeURIComponent('/课程/自己的课/小草');
const row = text => ({textContent:text,classList:{contains:()=>false}});
const panels=[{textContent:'other.mp4',querySelectorAll:()=>[row('other.mp4')]},
  {textContent:'video.mp4',querySelectorAll:()=>[row('video.mp4')]}];
const document={visibilityState:'visible',hasFocus:()=>true,
  querySelectorAll:selector=>selector==='.uploader-list'?panels:[]};
const page={tabs:async()=>[{page:'exact-page',url}],selectTab:async()=>{},getActivePage:()=> 'exact-page',
  evaluate:async source=>{
    if(source.includes('visibility: document.visibilityState, url: location.href'))return {visibility:'visible',url};
    if(source.includes('responsive:true'))return {responsive:true};
    return await vm.runInNewContext(source,{URL,URLSearchParams,document,location:new URL(url),
      navigator:{},window:{},AbortSignal,fetch:async()=>({json:async()=>({errno:0,list:[]})})});
  }};
spec.func(page,{file:'/tmp/video.mp4','target-name':'video.mp4','claim-id':'job-12345678','inspect-only':true})
  .then(value=>process.stdout.write(JSON.stringify(value)))
  .catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
"""
    node = shutil.which("node") or "/opt/homebrew/bin/node"
    result = subprocess.run([node, "-e", script, str(adapter)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    queue = json.loads(result.stdout)[0]["surfaceState"]["transferQueue"]
    assert queue["panelCount"] == 2
    assert queue["rowCount"] == 2
    assert queue["targetCount"] == 1
    assert queue["complete"] is False


@pytest.mark.parametrize("mode", ["upload", "inspect", "activate", "activation_denied", "missing", "ambiguous", "wrong_folder", "hidden", "foreground_ambiguous", "restore_missing", "restore_existing", "restore_ambiguous", "restore_present", "restore_activate_conflict", "restore_wrong_folder", "restore_unrelated", "restore_hidden", "recover_empty", "recover_active", "recover_multi", "recover_reactivated", "recover_missing", "recover_wrong_page", "recover_changed_after"])
def test_upload_selects_exact_site_tab_before_file_input(mode):
    adapter = Path(__file__).parents[1] / "opencli/clis/baidu-netdisk/upload.js"
    script = r"""
const fs = require('fs');
const vm = require('vm');
let spec;
const mode = process.argv[2];
let foregroundRequests = 0;
let pageTitle = '百度网盘';
const sandbox = {randomUUID: () => 'test-marker', process: {...process, platform:'darwin'}, execFileSync: (cmd, argv) => {
    foregroundRequests++;
    if(pageTitle !== 'Xiaocao uploader test-marker' || !argv.includes(pageTitle)) throw Error('native title not bound to retained page');
    if(!argv[1].includes('title of tab i of w is expectedTitle')) throw Error('ambiguous native URLs not disambiguated');
    if(cmd !== '/usr/bin/osascript' || !argv.includes('https://pan.baidu.com/disk/main#/index?category=all&path=%2F%E8%AF%BE%E7%A8%8B%2F%E8%87%AA%E5%B7%B1%E7%9A%84%E8%AF%BE%2F%E5%B0%8F%E8%8D%89')) throw Error('wrong native target');
    if(mode === 'foreground_ambiguous') throw Error('ambiguous native window');
    return 'foreground_requested';
  }, URL, URLSearchParams, cli: value => spec = value, Strategy: {UI: 'UI'},
  ArgumentError: Error, AuthRequiredError: Error, CommandExecutionError: Error};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8').replace(/import[\s\S]*?from '[^']+';/g, ''), sandbox);
let foreground = false;
let activated = false, attachments = 0, navigations = 0;
const emptySurface = () => ({transferQueue:{panelCount:1,rowCount:0,targetCount:0},
  targetInTransferUi:false,receiptMatchesTarget:false,targetUiRows:[],inputs:[{targetAttached:false}]});
const nonemptySurface = () => ({...emptySurface(),transferQueue:{panelCount:1,rowCount:1,targetCount:1},
  targetInTransferUi:true,targetUiRows:[{}]});
const page = {
  tabs: async () => {
    if (mode === 'restore_unrelated') return [{page:'unrelated',url:'https://example.org/'}];
    const tab = {page: 'site-upload-page', url: 'https://pan.baidu.com/disk/main#/index?category=all&path=' + encodeURIComponent(['wrong_folder','restore_wrong_folder'].includes(mode) ? '/wrong' : '/课程/自己的课/小草')};
    return ['missing','restore_missing','recover_missing'].includes(mode) ? [] : ['ambiguous','restore_ambiguous'].includes(mode) ? [tab, {...tab, page:'other'}] : [tab];
  },
  goto: async () => {if(mode !== 'restore_missing') throw Error('BUG: navigated an already bound uploader'); navigations++;}, wait: async () => {},
  getActivePage: () => mode === 'recover_changed_after' && activated ? 'other-page' : 'site-upload-page',
  selectTab: async id => { if (id !== 'site-upload-page') throw Error('wrong page'); foreground = true; },
  click: async selector => { if (!foreground || !selector.includes('activation')) throw Error('wrong activation'); activated = mode !== 'activation_denied'; },
  evaluate: async source => {
    if (source.includes('const original = document.title')) {if(mode==='restore_hidden')throw Error('readback changed native title'); pageTitle='Xiaocao uploader test-marker'; return '百度网盘';}
    if (source.includes('if (document.title ===')) {pageTitle='百度网盘'; return;}
    if (source.includes('responsive:true')) return {responsive:true};
    if (source.includes('visibility: document.visibilityState, url: location.href')) return {visibility: ['hidden','foreground_ambiguous','restore_hidden'].includes(mode) ? 'hidden' : 'visible', x:0,y:101,w:1496,h:866,url:'https://pan.baidu.com/disk/main#/index?category=all&path=%2F%E8%AF%BE%E7%A8%8B%2F%E8%87%AA%E5%B7%B1%E7%9A%84%E8%AF%BE%2F%E5%B0%8F%E8%8D%89'};
    if (source.includes('const pageSize')) {
      const surface = mode === 'recover_active' ? nonemptySurface() : emptySurface();
      if(mode==='recover_multi')surface.transferQueue.panelCount=2;
      return {folderBound:true,authenticated:true,completeScan:true,exactCount:mode==='restore_present'?1:0,
        url:'https://pan.baidu.com/disk/main',surfaceState:surface};
    }
    if (source.includes('transferQueue: {panelCount:')) return mode === 'recover_reactivated' ? nonemptySurface() : emptySurface();
    if (source.includes('const inputs')) return {marked: true, matches: 1};
    if (source.includes('const headers')) return true;
    if (source.includes('userActive: navigator')) return {userActive: activated};
    return {claim: 'job-12345678', fileNames: ['video.mp4']};
  },
  uploadFiles: async selector => {
    attachments++;
    if (!foreground) throw Error('file chooser on background site page');
    if (!activated) throw Error('file chooser without user activation');
    return {uploaded: true, files: 1, target: selector, matches_n: 1, file_names: ['video.mp4']};
  },
};
spec.func(page, {file: '/tmp/video.mp4', 'target-name': 'video.mp4', 'claim-id': 'job-12345678',
  'inspect-only': ['inspect','missing','ambiguous','wrong_folder','hidden','foreground_ambiguous'].includes(mode), 'activate-only': ['activate','restore_activate_conflict'].includes(mode),
  'restore-readback-only': mode.startsWith('restore_'), 'recover-lost-context': mode.startsWith('recover_'),
  'expected-page': mode === 'recover_wrong_page' ? 'other-page' : 'site-upload-page'})
  .then(value => process.stdout.write(JSON.stringify({value, attachments,foregroundRequests,pageTitle,navigations})))
  .catch(error => {process.stdout.write(JSON.stringify({error: error.message, attachments,foregroundRequests,pageTitle,navigations})); process.exitCode = 1;});
"""
    node = shutil.which("node") or "/opt/homebrew/bin/node"
    result = subprocess.run([node, "-e", script, str(adapter), mode], capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["pageTitle"] == "百度网盘"
    assert payload["attachments"] == (1 if mode in {"upload", "recover_empty"} else 0)
    assert payload["navigations"] == (1 if mode == "restore_missing" else 0)
    assert payload["foregroundRequests"] == (1 if mode in {"hidden", "foreground_ambiguous"} else 0)
    if mode == "foreground_ambiguous":
        assert result.returncode == 1
        return
    if mode == "restore_activate_conflict":
        assert result.returncode == 1
        assert "cannot be combined" in payload["error"]
        return
    if mode == "restore_wrong_folder":
        assert result.returncode == 1
        assert "preserve it without navigation" in payload["error"]
        return
    if mode == "restore_unrelated":
        assert result.returncode == 1
        assert "Nonblank adapter pages" in payload["error"]
        return
    if mode.startswith("recover_") and mode != "recover_empty":
        assert result.returncode == 1
        return
    if mode in {"missing", "wrong_folder", "ambiguous", "restore_ambiguous"}:
        assert result.returncode == 1
        assert ("ambiguous" if mode in {"ambiguous", "restore_ambiguous"} else "must not navigate") in payload["error"]
        return
    if mode == "activation_denied":
        assert result.returncode == 1
        assert "did not establish user activation" in payload["error"]
    else:
        assert result.returncode == 0, result.stderr
        assert payload["value"][0]["status"] == {
            "upload": "upload_submitted", "inspect": "ready_to_upload", "hidden": "ready_to_upload", "activate": "activation_verified",
            "restore_missing": "ready_to_upload", "restore_existing": "ready_to_upload",
            "restore_present": "already_present", "restore_hidden": "ready_to_upload",
            "recover_empty": "upload_submitted"
        }[mode]
