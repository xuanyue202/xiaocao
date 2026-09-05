import json
from pathlib import Path
import shutil
import subprocess
import pytest


@pytest.mark.parametrize("mode", ["upload", "inspect", "activate", "activation_denied"])
def test_upload_selects_exact_site_tab_before_file_input(mode):
    adapter = Path(__file__).parents[1] / "opencli/clis/baidu-netdisk/upload.js"
    script = r"""
const fs = require('fs');
const vm = require('vm');
let spec;
const mode = process.argv[2];
const sandbox = {cli: value => spec = value, Strategy: {UI: 'UI'},
  ArgumentError: Error, AuthRequiredError: Error, CommandExecutionError: Error};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8').replace(/import[\s\S]*?from '[^']+';/g, ''), sandbox);
let foreground = false;
let activated = false, attachments = 0;
const page = {
  goto: async () => {}, wait: async () => {},
  getActivePage: () => 'site-upload-page',
  selectTab: async id => { if (id !== 'site-upload-page') throw Error('wrong page'); foreground = true; },
  click: async selector => { if (!foreground || !selector.includes('activation')) throw Error('wrong activation'); activated = mode !== 'activation_denied'; },
  evaluate: async source => {
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
  'inspect-only': mode === 'inspect', 'activate-only': mode === 'activate'})
  .then(value => process.stdout.write(JSON.stringify({value, attachments})))
  .catch(error => {process.stdout.write(JSON.stringify({error: error.message, attachments})); process.exitCode = 1;});
"""
    node = shutil.which("node") or "/opt/homebrew/bin/node"
    result = subprocess.run([node, "-e", script, str(adapter), mode], capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["attachments"] == (1 if mode == "upload" else 0)
    if mode == "activation_denied":
        assert result.returncode == 1
        assert "did not establish user activation" in payload["error"]
    else:
        assert result.returncode == 0, result.stderr
        assert payload["value"][0]["status"] == {
            "upload": "upload_submitted", "inspect": "ready_to_upload", "activate": "activation_verified"
        }[mode]
