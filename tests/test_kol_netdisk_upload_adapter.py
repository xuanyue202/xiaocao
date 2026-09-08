import json
from pathlib import Path
import shutil
import subprocess
import pytest


@pytest.mark.parametrize("mode", ["upload", "inspect", "activate", "activation_denied", "missing", "ambiguous", "wrong_folder", "hidden", "foreground_ambiguous"])
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
let activated = false, attachments = 0;
const page = {
  tabs: async () => {
    const tab = {page: 'site-upload-page', url: 'https://pan.baidu.com/disk/main#/index?category=all&path=' + encodeURIComponent(mode === 'wrong_folder' ? '/wrong' : '/课程/自己的课/小草')};
    return mode === 'missing' ? [] : mode === 'ambiguous' ? [tab, {...tab, page:'other'}] : [tab];
  },
  goto: async () => {throw Error('BUG: navigated an already bound uploader');}, wait: async () => {},
  getActivePage: () => 'site-upload-page',
  selectTab: async id => { if (id !== 'site-upload-page') throw Error('wrong page'); foreground = true; },
  click: async selector => { if (!foreground || !selector.includes('activation')) throw Error('wrong activation'); activated = mode !== 'activation_denied'; },
  evaluate: async source => {
    if (source.includes('const original = document.title')) {pageTitle='Xiaocao uploader test-marker'; return '百度网盘';}
    if (source.includes('if (document.title ===')) {pageTitle='百度网盘'; return;}
    if (source.includes('responsive:true')) return {responsive:true};
    if (source.includes('visibility: document.visibilityState, url: location.href')) return {visibility: ['hidden','foreground_ambiguous'].includes(mode) ? 'hidden' : 'visible', x:0,y:101,w:1496,h:866,url:'https://pan.baidu.com/disk/main#/index?category=all&path=%2F%E8%AF%BE%E7%A8%8B%2F%E8%87%AA%E5%B7%B1%E7%9A%84%E8%AF%BE%2F%E5%B0%8F%E8%8D%89'};
    if (source.includes('const pageSize')) return {folderBound: true, authenticated: true, completeScan: true, exactCount: 0, url: 'https://pan.baidu.com/disk/main'};
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
  'inspect-only': ['inspect','missing','ambiguous','wrong_folder','hidden','foreground_ambiguous'].includes(mode), 'activate-only': mode === 'activate'})
  .then(value => process.stdout.write(JSON.stringify({value, attachments,foregroundRequests,pageTitle})))
  .catch(error => {process.stdout.write(JSON.stringify({error: error.message, attachments,foregroundRequests,pageTitle})); process.exitCode = 1;});
"""
    node = shutil.which("node") or "/opt/homebrew/bin/node"
    result = subprocess.run([node, "-e", script, str(adapter), mode], capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["pageTitle"] == "百度网盘"
    assert payload["attachments"] == (1 if mode == "upload" else 0)
    assert payload["foregroundRequests"] == (1 if mode in {"hidden", "foreground_ambiguous"} else 0)
    if mode == "foreground_ambiguous":
        assert result.returncode == 1
        return
    if mode in {"missing", "wrong_folder", "ambiguous"}:
        assert result.returncode == 1
        assert ("ambiguous" if mode == "ambiguous" else "must not navigate") in payload["error"]
        return
    if mode == "activation_denied":
        assert result.returncode == 1
        assert "did not establish user activation" in payload["error"]
    else:
        assert result.returncode == 0, result.stderr
        assert payload["value"][0]["status"] == {
            "upload": "upload_submitted", "inspect": "ready_to_upload", "hidden": "ready_to_upload", "activate": "activation_verified"
        }[mode]
