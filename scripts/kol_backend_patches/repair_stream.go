package download

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/GopeedLab/gopeed/pkg/base"
	"github.com/GopeedLab/gopeed/pkg/util"
)

type StreamRepairReceipt struct {
	ID             string      `json:"id"`
	PreviousName   string      `json:"previous_name"`
	PreviousSHA256 string      `json:"previous_sha256"`
	Name           string      `json:"name"`
	Revision       string      `json:"revision"`
	Status         base.Status `json:"status"`
}

func repairProbeDuration(name string) (float64, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	output, err := exec.CommandContext(ctx, "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", name).Output()
	if err != nil {
		return 0, fmt.Errorf("repair artifact probe failed")
	}
	var data struct {
		Format struct {
			Duration string `json:"duration"`
		} `json:"format"`
	}
	if json.Unmarshal(output, &data) != nil {
		return 0, fmt.Errorf("repair artifact probe invalid")
	}
	value, err := strconv.ParseFloat(data.Format.Duration, 64)
	if err != nil || math.IsNaN(value) || math.IsInf(value, 0) {
		return 0, fmt.Errorf("repair artifact duration invalid")
	}
	return value, nil
}
func streamRepairPlan(task *Task, candidate, live, originalSHA string, probe func(string) (float64, error)) (StreamRepairReceipt, error) {
	if task == nil || task.Meta == nil || task.Meta.Req == nil || task.Meta.Opts == nil || task.Protocol != "stream" {
		return StreamRepairReceipt{}, fmt.Errorf("original stream task unavailable")
	}
	labels := task.Meta.Req.Labels
	if labels["capture_id"] != candidate || labels["live_id"] != live || candidate == "" || live == "" || labels["type"] != "live_capture" || labels["compress"] != "true" || labels["compress_inline"] != "true" {
		return StreamRepairReceipt{}, fmt.Errorf("original compressed capture binding invalid")
	}
	if labels["media_repair_revision"] != "" {
		if labels["media_repair_previous_sha256"] != originalSHA {
			return StreamRepairReceipt{}, fmt.Errorf("repair revision already consumed")
		}
		return StreamRepairReceipt{task.ID, labels["media_repair_previous_name"], originalSHA, task.Meta.Opts.Name, labels["media_repair_revision"], task.Status}, nil
	}
	if task.Status != base.DownloadStatusDone {
		return StreamRepairReceipt{}, fmt.Errorf("repair requires exact previously completed task")
	}
	if len(originalSHA) != 64 {
		return StreamRepairReceipt{}, fmt.Errorf("repair artifact hash invalid")
	}
	path := task.Meta.SingleFilepath()
	file, err := os.Open(path)
	if err != nil {
		return StreamRepairReceipt{}, fmt.Errorf("original artifact unavailable")
	}
	hash := sha256.New()
	_, err = io.Copy(hash, file)
	file.Close()
	if err != nil || hex.EncodeToString(hash.Sum(nil)) != originalSHA {
		return StreamRepairReceipt{}, fmt.Errorf("original artifact changed")
	}
	expected, err := strconv.ParseFloat(labels["hls_duration_sec"], 64)
	if err != nil || math.IsNaN(expected) || math.IsInf(expected, 0) || expected <= 0 {
		return StreamRepairReceipt{}, fmt.Errorf("original finite duration missing")
	}
	actual, err := probe(path)
	if err != nil {
		return StreamRepairReceipt{}, err
	}
	if math.Abs(actual-expected) <= 2 {
		return StreamRepairReceipt{}, fmt.Errorf("complete artifact cannot be restarted")
	}
	oldName := filepath.Base(path)
	if !strings.Contains(oldName, "-compressed") || filepath.Ext(oldName) != ".mp4" {
		return StreamRepairReceipt{}, fmt.Errorf("original compressed filename invalid")
	}
	name, err := util.CheckDuplicateAndRename(path)
	if err != nil || name == oldName {
		return StreamRepairReceipt{}, fmt.Errorf("revision path unavailable")
	}
	revision := sha256.Sum256([]byte(task.ID + ":" + candidate + ":" + live + ":" + originalSHA + ":" + name))
	return StreamRepairReceipt{task.ID, oldName, originalSHA, name, hex.EncodeToString(revision[:]), base.DownloadStatusPause}, nil
}

// PrepareIncompleteStreamRevision retains the old file and original task ID.
// It only persists a paused revision; the ordinary exact-task resume starts it.
func (d *Downloader) PrepareIncompleteStreamRevision(id, candidate, live, originalSHA string) (StreamRepairReceipt, error) {
	task := d.GetTask(id)
	if task == nil {
		return StreamRepairReceipt{}, ErrTaskNotFound
	}
	task.statusLock.Lock()
	defer task.statusLock.Unlock()
	task.lock.Lock()
	defer task.lock.Unlock()
	d.checkDuplicateLock.Lock()
	defer d.checkDuplicateLock.Unlock()
	receipt, err := streamRepairPlan(task, candidate, live, originalSHA, repairProbeDuration)
	if err != nil {
		return receipt, err
	}
	if task.Meta.Req.Labels["media_repair_revision"] != "" {
		return receipt, nil
	}
	rollback, reserveErr := reserveStreamRevision(task, receipt)
	if reserveErr != nil {
		return StreamRepairReceipt{}, reserveErr
	}
	committed := false
	defer func() {
		if !committed {
			rollback()
		}
	}()
	// Persist a cloned projection first. Failed persistence changes no live state.
	projection := task.clone()
	projection.Meta.Opts.Name = receipt.Name
	projection.Meta.Req.Labels["media_repair_revision"] = receipt.Revision
	projection.Meta.Req.Labels["media_repair_previous_sha256"] = originalSHA
	projection.Meta.Req.Labels["media_repair_previous_name"] = receipt.PreviousName
	projection.Meta.Req.Labels["media_repair_task_id"] = task.ID
	projection.updateStatus(base.DownloadStatusPause)
	if err = d.storage.Put(bucketTask, id, projection); err != nil {
		return StreamRepairReceipt{}, err
	}
	committed = true
	task.Meta.Opts.Name = receipt.Name
	task.Meta.Req.Labels = projection.Meta.Req.Labels
	task.updateStatus(base.DownloadStatusPause)
	return receipt, nil
}

// Reserve the revision path now, so ordinary auto-renaming tasks cannot choose it
// while this task remains paused. Rollback removes only the inode we created.
func reserveStreamRevision(task *Task, receipt StreamRepairReceipt) (func(), error) {
	name := filepath.Join(task.Meta.Opts.Path, receipt.Name)
	file, err := os.OpenFile(name, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return nil, fmt.Errorf("revision output already occupied")
	}
	stamp, _ := file.Stat()
	markerCreated := false
	removeOwn := func() {
		current, e := os.Stat(name)
		if e == nil && stamp != nil && os.SameFile(stamp, current) && current.Size() == 0 {
			_ = os.Remove(name)
			if markerCreated {
				_ = os.Remove(name + ".reservation.json")
			}
		}
	}
	if err = file.Sync(); err != nil {
		file.Close()
		removeOwn()
		return nil, err
	}
	file.Close()
	marker := map[string]string{"revision": receipt.Revision, "previous_sha256": receipt.PreviousSHA256, "task_id": task.ID, "candidate_id": task.Meta.Req.Labels["capture_id"], "live_id": task.Meta.Req.Labels["live_id"]}
	data, _ := json.Marshal(marker)
	proof, err := os.OpenFile(name+".reservation.json", os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		removeOwn()
		return nil, fmt.Errorf("revision reservation unavailable")
	}
	markerCreated = true
	_, err = proof.Write(data)
	if err == nil {
		err = proof.Sync()
	}
	closeErr := proof.Close()
	if err != nil || closeErr != nil {
		removeOwn()
		return nil, fmt.Errorf("revision reservation persistence failed")
	}
	return removeOwn, nil
}
