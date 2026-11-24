package download

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/GopeedLab/gopeed/pkg/base"
	"github.com/GopeedLab/gopeed/pkg/util"
)

var recordedHexSHA = regexp.MustCompile(`^[0-9a-f]{64}$`)
var recordedResource = regexp.MustCompile(`^v_[0-9a-f]{24}$`)
var recordedFile = regexp.MustCompile(`^[0-9]{8,}$`)
var recordedMediaComponent = regexp.MustCompile(`^[0-9a-f]{8}([0-9]{8,})$`)
var recordedPlaylist = regexp.MustCompile(`^v\.f[0-9]+\.m3u8$`)

// RecordedRepairTaskSnapshot is read-only and does not expose a new ticket.
// The API keeps this clone inside the process and never serializes its URL.
func (d *Downloader) RecordedRepairTaskSnapshot(id string) (*Task, error) {
	d.lock.Lock()
	defer d.lock.Unlock()
	task := d.GetTask(id)
	if task == nil {
		return nil, ErrTaskNotFound
	}
	for _, other := range d.tasks {
		if other != nil && (other.Status == base.DownloadStatusRunning || other.Status == base.DownloadStatusReady || other.Status == base.DownloadStatusWait) {
			return nil, fmt.Errorf("active provider task blocks revision")
		}
	}
	task.statusLock.Lock()
	defer task.statusLock.Unlock()
	task.lock.Lock()
	defer task.lock.Unlock()
	if task.Status != base.DownloadStatusPause && task.Status != base.DownloadStatusError {
		return nil, fmt.Errorf("recorded terminal task is not stopped")
	}
	return task.clone(), nil
}

// recordedTerminalPlan is deliberately read-only. The old media and checkpoint
// remain immutable; a revision reserves a separate output on the same task.
func recordedTerminalPlan(task *Task, candidate, resource, fileID, partialSHA, manifestSHA, resourceSHA, aliasID string) (StreamRepairReceipt, error) {
	if task == nil || task.Meta == nil || task.Meta.Req == nil || task.Meta.Opts == nil || task.Meta.Res == nil ||
		len(task.Meta.Res.Files) != 1 || task.Meta.Res.Files[0] == nil || task.Meta.Res.Files[0].Path != "" ||
		task.Protocol != "stream" || (task.Status != base.DownloadStatusPause && task.Status != base.DownloadStatusError) {
		return StreamRepairReceipt{}, fmt.Errorf("recorded terminal task is not stopped")
	}
	labels := task.Meta.Req.Labels
	if candidate == "" || aliasID == "" || !recordedResource.MatchString(resource) || !recordedFile.MatchString(fileID) ||
		!recordedHexSHA.MatchString(partialSHA) || !recordedHexSHA.MatchString(manifestSHA) || !recordedHexSHA.MatchString(resourceSHA) ||
		labels["capture_id"] != candidate || labels["recorded_resource_id"] != resource ||
		labels["recorded_media_file_id"] != fileID || labels["type"] != "live_capture" ||
		labels["source"] != "xiaocao" || labels["compress_inline"] != "true" ||
		labels["checkpoint_basis"] != "verified_hls_segments" || labels["hls_finite"] != "true" {
		return StreamRepairReceipt{}, fmt.Errorf("recorded terminal task binding invalid")
	}
	source, err := url.Parse(task.Meta.Req.URL)
	if err != nil || source.Scheme != "https" || source.User != nil || source.Fragment != "" ||
		(source.Host != "encrypt-k-vod.xet.tech" && source.Host != "t-vod.h5.xed.plus") {
		return StreamRepairReceipt{}, fmt.Errorf("recorded original resource invalid")
	}
	fileMatches := 0
	for _, part := range strings.Split(source.Path, "/") {
		if match := recordedMediaComponent.FindStringSubmatch(part); len(match) == 2 {
			if match[1] != fileID {
				return StreamRepairReceipt{}, fmt.Errorf("recorded file binding changed")
			}
			fileMatches++
		}
	}
	if fileMatches != 1 || !strings.Contains(source.Path, "/drm/") || !recordedPlaylist.MatchString(filepath.Base(source.Path)) {
		return StreamRepairReceipt{}, fmt.Errorf("recorded media path invalid")
	}
	source.RawQuery = ""
	source.ForceQuery = false
	resourceHash := sha256.Sum256([]byte(source.String()))
	if hex.EncodeToString(resourceHash[:]) != resourceSHA {
		return StreamRepairReceipt{}, fmt.Errorf("recorded original resource changed")
	}
	existingRevision := labels["media_repair_revision"]
	name := task.Meta.SingleFilepath()
	if existingRevision != "" {
		previous := labels["media_repair_previous_name"]
		if task.Status != base.DownloadStatusPause || !recordedHexSHA.MatchString(existingRevision) ||
			labels["recorded_ticket_repair_revision"] != existingRevision || labels["recorded_ticket_alias_id"] != aliasID ||
			labels["media_repair_previous_sha256"] != partialSHA || labels["recorded_original_manifest_sha256"] != manifestSHA ||
			labels["media_repair_task_id"] != task.ID || previous == "" || filepath.Base(previous) != previous ||
			filepath.Base(task.Meta.Opts.Name) != task.Meta.Opts.Name {
			return StreamRepairReceipt{}, fmt.Errorf("recorded revision binding changed")
		}
		name = filepath.Join(task.Meta.Opts.Path, previous)
	}
	if !strings.Contains(filepath.Base(name), "-compressed") || filepath.Ext(name) != ".mp4" {
		return StreamRepairReceipt{}, fmt.Errorf("recorded partial output invalid")
	}
	info, err := os.Lstat(name)
	if err != nil || !info.Mode().IsRegular() || info.Size() <= 0 {
		return StreamRepairReceipt{}, fmt.Errorf("recorded partial output unavailable")
	}
	file, err := os.Open(name)
	if err != nil {
		return StreamRepairReceipt{}, fmt.Errorf("recorded partial output unavailable")
	}
	opened, err := file.Stat()
	if err != nil || !opened.Mode().IsRegular() || !os.SameFile(info, opened) {
		file.Close()
		return StreamRepairReceipt{}, fmt.Errorf("recorded partial output changed")
	}
	hash := sha256.New()
	_, err = io.Copy(hash, file)
	after, statErr := file.Stat()
	file.Close()
	current, pathErr := os.Lstat(name)
	if err != nil || statErr != nil || pathErr != nil || !current.Mode().IsRegular() ||
		!os.SameFile(opened, current) || after.Size() != opened.Size() || !after.ModTime().Equal(opened.ModTime()) ||
		hex.EncodeToString(hash.Sum(nil)) != partialSHA {
		return StreamRepairReceipt{}, fmt.Errorf("recorded partial output changed")
	}
	cache := name + ".hls-cache"
	info, err = os.Lstat(cache)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return StreamRepairReceipt{}, fmt.Errorf("recorded checkpoint unavailable")
	}
	readSmall := func(path string) ([]byte, error) {
		st, err := os.Lstat(path)
		if err != nil || !st.Mode().IsRegular() || st.Size() > 4096 {
			return nil, fmt.Errorf("recorded checkpoint file invalid")
		}
		f, err := os.Open(path)
		if err != nil {
			return nil, fmt.Errorf("recorded checkpoint file invalid")
		}
		defer f.Close()
		opened, err := f.Stat()
		if err != nil || !opened.Mode().IsRegular() || !os.SameFile(st, opened) {
			return nil, fmt.Errorf("recorded checkpoint file changed")
		}
		data, err := io.ReadAll(io.LimitReader(f, 4097))
		after, statErr := f.Stat()
		current, pathErr := os.Lstat(path)
		if err != nil || statErr != nil || pathErr != nil || len(data) > 4096 ||
			!current.Mode().IsRegular() || !os.SameFile(opened, current) ||
			after.Size() != opened.Size() || !after.ModTime().Equal(opened.ModTime()) {
			return nil, fmt.Errorf("recorded checkpoint file changed")
		}
		return data, nil
	}
	terminal, err := readSmall(filepath.Join(cache, "terminal.json"))
	if err != nil {
		return StreamRepairReceipt{}, err
	}
	var stopped struct {
		Status int `json:"status"`
	}
	if json.Unmarshal(terminal, &stopped) != nil || (stopped.Status != 401 && stopped.Status != 403) {
		return StreamRepairReceipt{}, fmt.Errorf("recorded checkpoint is not auth terminal")
	}
	data, err := readSmall(filepath.Join(cache, "binding.json"))
	if err != nil {
		return StreamRepairReceipt{}, err
	}
	var binding struct {
		Binding, Manifest string
		Segments          int
	}
	oldBinding := sha256.Sum256([]byte(candidate + ":" + labels["live_id"] + "\n" + task.Meta.Req.URL))
	if json.Unmarshal(data, &binding) != nil || binding.Binding != hex.EncodeToString(oldBinding[:]) ||
		binding.Manifest != manifestSHA || binding.Segments <= 0 ||
		fmt.Sprint(binding.Segments) != labels["checkpoint_segments"] {
		return StreamRepairReceipt{}, fmt.Errorf("recorded checkpoint manifest changed")
	}
	newName := task.Meta.Opts.Name
	if existingRevision == "" {
		newName, err = util.CheckDuplicateAndRename(name)
		if err != nil || newName == filepath.Base(name) {
			return StreamRepairReceipt{}, fmt.Errorf("recorded revision output unavailable")
		}
	}
	revision := sha256.Sum256([]byte(strings.Join([]string{task.ID, candidate, resource, fileID, partialSHA, manifestSHA, resourceSHA, aliasID, newName}, "\n")))
	revisionText := hex.EncodeToString(revision[:])
	if existingRevision != "" {
		// Only an untouched reservation can be reconciled. Once a resume may
		// have run, the coordinator must reconcile its own exact resume claim.
		if revisionText != existingRevision || newName == filepath.Base(name) {
			return StreamRepairReceipt{}, fmt.Errorf("recorded revision changed")
		}
		target := filepath.Join(task.Meta.Opts.Path, newName)
		reserved, err := os.Lstat(target)
		if err != nil || !reserved.Mode().IsRegular() || reserved.Size() != 0 {
			return StreamRepairReceipt{}, fmt.Errorf("recorded revision was used")
		}
		if _, err := os.Lstat(target + ".hls-cache"); !os.IsNotExist(err) {
			return StreamRepairReceipt{}, fmt.Errorf("recorded revision checkpoint exists")
		}
		if _, err := os.Lstat(target + ".recorded-started"); !os.IsNotExist(err) {
			return StreamRepairReceipt{}, fmt.Errorf("recorded revision resume requires reconciliation")
		}
		marker, err := readSmall(target + ".reservation.json")
		if err != nil {
			return StreamRepairReceipt{}, err
		}
		var proof map[string]string
		if json.Unmarshal(marker, &proof) != nil || len(proof) != 5 || proof["revision"] != revisionText ||
			proof["previous_sha256"] != partialSHA || proof["task_id"] != task.ID ||
			proof["candidate_id"] != candidate || proof["live_id"] != labels["live_id"] {
			return StreamRepairReceipt{}, fmt.Errorf("recorded revision reservation changed")
		}
	}
	return StreamRepairReceipt{ID: task.ID, PreviousName: filepath.Base(name), PreviousSHA256: partialSHA,
		Name: newName, Revision: revisionText, Status: base.DownloadStatusPause}, nil
}

// PrepareRecordedTerminalRevision durably reserves a fresh output for the
// existing task. It never starts, resumes, deletes, or changes the old files.
// Actual ticket validation and process-local installation are performed by the
// API layer before a separate, independently claimed resume.
func (d *Downloader) PrepareRecordedTerminalRevision(id, candidate, resource, fileID, partialSHA, manifestSHA, resourceSHA, aliasID string) (StreamRepairReceipt, error) {
	d.lock.Lock()
	defer d.lock.Unlock()
	task := d.GetTask(id)
	if task == nil {
		return StreamRepairReceipt{}, ErrTaskNotFound
	}
	for _, other := range d.tasks {
		if other != nil && (other.Status == base.DownloadStatusRunning || other.Status == base.DownloadStatusReady || other.Status == base.DownloadStatusWait) {
			return StreamRepairReceipt{}, fmt.Errorf("active provider task blocks revision")
		}
	}
	task.statusLock.Lock()
	defer task.statusLock.Unlock()
	task.lock.Lock()
	defer task.lock.Unlock()
	d.checkDuplicateLock.Lock()
	defer d.checkDuplicateLock.Unlock()
	plan, err := recordedTerminalPlan(task, candidate, resource, fileID, partialSHA, manifestSHA, resourceSHA, aliasID)
	if err != nil {
		return StreamRepairReceipt{}, err
	}
	if task.Meta.Req.Labels["media_repair_revision"] != "" {
		return plan, nil
	}
	rollback, err := reserveStreamRevision(task, plan)
	if err != nil {
		return StreamRepairReceipt{}, err
	}
	committed := false
	defer func() {
		if !committed {
			rollback()
		}
	}()
	projection := task.clone()
	projection.Meta.Opts.Name = plan.Name
	projection.Meta.Req.Labels["media_repair_revision"] = plan.Revision
	projection.Meta.Req.Labels["media_repair_previous_sha256"] = partialSHA
	projection.Meta.Req.Labels["media_repair_previous_name"] = plan.PreviousName
	projection.Meta.Req.Labels["media_repair_task_id"] = task.ID
	projection.Meta.Req.Labels["recorded_ticket_repair_revision"] = plan.Revision
	projection.Meta.Req.Labels["recorded_ticket_alias_id"] = aliasID
	projection.Meta.Req.Labels["recorded_original_manifest_sha256"] = manifestSHA
	projection.Meta.Req.Labels["recorded_original_resource_sha256"] = resourceSHA
	projection.updateStatus(base.DownloadStatusPause)
	if err = d.storage.Put(bucketTask, id, projection); err != nil {
		return StreamRepairReceipt{}, err
	}
	committed = true
	task.Meta.Opts.Name = projection.Meta.Opts.Name
	task.Meta.Req.Labels = projection.Meta.Req.Labels
	task.updateStatus(base.DownloadStatusPause)
	return plan, nil
}

// StartRecordedTerminalRevision starts only the reconciled task and never uses
// Continue, whose capacity policy can pause unrelated tasks. The caller owns a
// durable exact resume claim before invoking this method.
func (d *Downloader) StartRecordedTerminalRevision(id, revision string) error {
	return d.startRecordedTerminalRevision(id, revision, d.doStart)
}

func (d *Downloader) startRecordedTerminalRevision(id, revision string, start func(*Task) error) error {
	d.lock.Lock()
	defer d.lock.Unlock()
	if !recordedHexSHA.MatchString(revision) || id == "" {
		return fmt.Errorf("recorded resume binding invalid")
	}
	task := d.GetTask(id)
	if task == nil {
		return ErrTaskNotFound
	}
	for _, other := range d.tasks {
		if other == nil {
			continue
		}
		other.statusLock.Lock()
		active := other.Status == base.DownloadStatusRunning || other.Status == base.DownloadStatusReady || other.Status == base.DownloadStatusWait
		other.statusLock.Unlock()
		if active {
			return fmt.Errorf("active provider task blocks recorded resume")
		}
	}
	task.statusLock.Lock()
	task.lock.Lock()
	valid := task.Status == base.DownloadStatusPause && task.Meta != nil && task.Meta.Req != nil && task.Meta.Opts != nil &&
		task.Meta.Req.Labels["recorded_ticket_repair_revision"] == revision && task.Meta.Req.Labels["media_repair_revision"] == revision &&
		task.Meta.Req.Labels["media_repair_task_id"] == id
	if valid {
		labels := task.Meta.Req.Labels
		plan, err := recordedTerminalPlan(task, labels["capture_id"], labels["recorded_resource_id"], labels["recorded_media_file_id"],
			labels["media_repair_previous_sha256"], labels["recorded_original_manifest_sha256"],
			labels["recorded_original_resource_sha256"], labels["recorded_ticket_alias_id"])
		valid = err == nil && plan.Revision == revision
	}
	task.lock.Unlock()
	task.statusLock.Unlock()
	if !valid {
		return fmt.Errorf("recorded task revision is not an untouched paused reservation")
	}
	return start(task)
}
