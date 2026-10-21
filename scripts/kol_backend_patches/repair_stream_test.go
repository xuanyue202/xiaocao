package download

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/GopeedLab/gopeed/internal/fetcher"
	"github.com/GopeedLab/gopeed/pkg/base"
	"github.com/GopeedLab/gopeed/pkg/util"
)

func repairTaskFixture(t *testing.T) (*Task, string) {
	t.Helper()
	root := t.TempDir()
	name := "original-compressed.mp4"
	data := []byte("retain incomplete original")
	if err := os.WriteFile(filepath.Join(root, name), data, 0600); err != nil {
		t.Fatal(err)
	}
	hash := sha256.Sum256(data)
	task := &Task{ID: "original-task", Protocol: "stream", Status: base.DownloadStatusDone, Progress: &Progress{}, Meta: &fetcher.FetcherMeta{
		Req:  &base.Request{URL: "https://example.test/replay.m3u8?token=private", Labels: map[string]string{"capture_id": "original-candidate", "live_id": "original-live", "type": "live_capture", "compress": "true", "compress_inline": "true", "hls_duration_sec": "6228.206"}},
		Opts: &base.Options{Path: root, Name: name}, Res: &base.Resource{Files: []*base.FileInfo{{Name: name}}},
	}}
	initTask(task)
	return task, hex.EncodeToString(hash[:])
}
func TestStreamRepairPlanRejectsWrongIdentityOrCompleteArtifact(t *testing.T) {
	for _, invalid := range []string{"hash", "candidate", "live", "running", "duration", "complete"} {
		t.Run(invalid, func(t *testing.T) {
			task, hash := repairTaskFixture(t)
			candidate, live := "original-candidate", "original-live"
			actual := 6190.762887
			switch invalid {
			case "hash":
				hash = fmt.Sprintf("%064d", 0)
			case "candidate":
				candidate = "other"
			case "live":
				live = "other"
			case "running":
				task.Status = base.DownloadStatusRunning
			case "duration":
				task.Meta.Req.Labels["hls_duration_sec"] = "nan"
			case "complete":
				actual = 6228.206
			}
			if _, err := streamRepairPlan(task, candidate, live, hash, func(string) (float64, error) { return actual, nil }); err == nil {
				t.Fatal("invalid repair accepted")
			}
			if task.Meta.Opts.Name != "original-compressed.mp4" {
				t.Fatal("failed plan mutated original task")
			}
		})
	}
}
func TestStreamRepairPreparationPreservesTaskAndOriginalFile(t *testing.T) {
	task, hash := repairTaskFixture(t)
	receipt, err := streamRepairPlan(task, "original-candidate", "original-live", hash, func(string) (float64, error) { return 6190.762887, nil })
	if err != nil {
		t.Fatal(err)
	}
	if receipt.ID != task.ID || receipt.Name != "original-compressed (1).mp4" || receipt.PreviousSHA256 != hash {
		t.Fatal("revision identity changed")
	}
	oldPath := task.Meta.SingleFilepath()
	before, _ := os.ReadFile(oldPath)
	// Exercise durable preparation and its idempotency with a deterministic probe.
	bin := t.TempDir()
	script := []byte("#!/bin/sh\nprintf '{\"format\":{\"duration\":\"6190.762887\"}}'\n")
	if err = os.WriteFile(filepath.Join(bin, "ffprobe"), script, 0700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
	d := NewDownloader(&DownloaderConfig{StorageDir: t.TempDir()})
	if err = d.Setup(); err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	d.tasks = append(d.tasks, task)
	first, err := d.PrepareIncompleteStreamRevision(task.ID, "original-candidate", "original-live", hash)
	if err != nil {
		t.Fatal(err)
	}
	second, err := d.PrepareIncompleteStreamRevision(task.ID, "original-candidate", "original-live", hash)
	if err != nil {
		t.Fatal(err)
	}
	if first != second || task.ID != "original-task" || task.Status != base.DownloadStatusPause || task.Meta.Opts.Name != first.Name {
		t.Fatal("same-task revision replay changed identity")
	}
	after, _ := os.ReadFile(oldPath)
	if string(after) != string(before) {
		t.Fatal("original bytes were overwritten")
	}
	reserved, err := os.Stat(filepath.Join(task.Meta.Opts.Path, first.Name))
	if err != nil || reserved.Size() != 0 {
		t.Fatal("paused revision did not reserve an empty output")
	}
	next, err := util.CheckDuplicateAndRename(oldPath)
	if err != nil || next == first.Name {
		t.Fatal("other task can choose the paused reservation")
	}

}
