package download

import (
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/GopeedLab/gopeed/pkg/base"
)

const recordedTestURL = "https://encrypt-k-vod.xet.tech/account/c700e05f5001834828749775294/drm/v.f123.m3u8"

func recordedTestResourceHash() string {
	v := sha256.Sum256([]byte(recordedTestURL))
	return hex.EncodeToString(v[:])
}

func recordedTerminalFixture(t *testing.T) (*Task, string, string) {
	t.Helper()
	task, partial := repairTaskFixture(t)
	task.ID = "recorded-terminal-task"
	task.Meta.Req.URL = recordedTestURL + "?secret=old"
	task.Status = base.DownloadStatusPause
	labels := task.Meta.Req.Labels
	labels["source"] = "xiaocao"
	labels["recorded_resource_id"] = "v_" + strings.Repeat("a", 24)
	labels["recorded_media_file_id"] = "5001834828749775294"
	labels["hls_finite"] = "true"
	labels["checkpoint_basis"] = "verified_hls_segments"
	labels["checkpoint_segments"] = "2"
	manifest := strings.Repeat("b", 64)
	cache := task.Meta.SingleFilepath() + ".hls-cache"
	if err := os.Mkdir(cache, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(cache, "terminal.json"), []byte(`{"status":403}`), 0600); err != nil {
		t.Fatal(err)
	}
	bound := sha256.Sum256([]byte(labels["capture_id"] + ":" + labels["live_id"] + "\n" + task.Meta.Req.URL))
	if err := os.WriteFile(filepath.Join(cache, "binding.json"), []byte(`{"Binding":"`+hex.EncodeToString(bound[:])+`","Manifest":"`+manifest+`","Segments":2}`), 0600); err != nil {
		t.Fatal(err)
	}
	return task, partial, manifest
}

func TestRecordedTerminalPlanKeepsOriginalAndRequiresExactBinding(t *testing.T) {
	task, partial, manifest := recordedTerminalFixture(t)
	resource, fileID := task.Meta.Req.Labels["recorded_resource_id"], task.Meta.Req.Labels["recorded_media_file_id"]
	name := task.Meta.SingleFilepath()
	before, _ := os.ReadFile(name)
	plan, err := recordedTerminalPlan(task, "original-candidate", resource, fileID, partial, manifest, recordedTestResourceHash(), "fresh-alias")
	if err != nil {
		t.Fatal(err)
	}
	if plan.ID != task.ID || plan.PreviousName != filepath.Base(name) || plan.Name == plan.PreviousName || task.Meta.SingleFilepath() != name {
		t.Fatal("planning changed original task or output")
	}
	after, _ := os.ReadFile(name)
	if string(before) != string(after) {
		t.Fatal("original file changed")
	}
	for _, bad := range []struct{ candidate, resource, file, hash, manifest, alias string }{
		{"wrong", resource, fileID, partial, manifest, "fresh-alias"},
		{"original-candidate", resource, "5001834828749775295", partial, manifest, "fresh-alias"},
		{"original-candidate", resource, fileID, strings.Repeat("0", 64), manifest, "fresh-alias"},
		{"original-candidate", resource, fileID, partial, strings.Repeat("0", 64), "fresh-alias"},
		{"original-candidate", resource, fileID, partial, manifest, ""},
	} {
		if _, err := recordedTerminalPlan(task, bad.candidate, bad.resource, bad.file, bad.hash, bad.manifest, recordedTestResourceHash(), bad.alias); err == nil {
			t.Fatal("changed binding accepted")
		}
	}
	if _, err := recordedTerminalPlan(task, "original-candidate", resource, fileID, partial, manifest, strings.Repeat("0", 64), "fresh-alias"); err == nil {
		t.Fatal("changed resource path accepted")
	}
}

func TestRecordedTerminalPreparationReservesSameTaskWithoutStarting(t *testing.T) {
	task, partial, manifest := recordedTerminalFixture(t)
	resource, fileID := task.Meta.Req.Labels["recorded_resource_id"], task.Meta.Req.Labels["recorded_media_file_id"]
	original := task.Meta.SingleFilepath()
	before, _ := os.ReadFile(original)
	d := NewDownloader(&DownloaderConfig{StorageDir: t.TempDir()})
	if err := d.storage.Setup([]string{bucketTask, bucketSave, bucketConfig}); err != nil {
		t.Fatal(err)
	}
	defer d.storage.Close()
	d.tasks = []*Task{task}
	snapshot, err := d.RecordedRepairTaskSnapshot(task.ID)
	if err != nil || snapshot.ID != task.ID || snapshot.Meta.Opts.Name != task.Meta.Opts.Name {
		t.Fatal("original stopped task snapshot unavailable")
	}
	snapshot.Meta.Req.Labels["capture_id"] = "changed-copy"
	if task.Meta.Req.Labels["capture_id"] != "original-candidate" {
		t.Fatal("snapshot modified live task")
	}
	result, err := d.PrepareRecordedTerminalRevision(task.ID, "original-candidate", resource, fileID, partial, manifest, recordedTestResourceHash(), "fresh-alias")
	if err != nil {
		t.Fatal(err)
	}
	if result.ID != task.ID || task.Status != base.DownloadStatusPause || task.Meta.Opts.Name != result.Name ||
		task.Meta.Req.Labels["recorded_ticket_repair_revision"] != result.Revision {
		t.Fatal("task binding changed")
	}
	after, _ := os.ReadFile(original)
	if string(before) != string(after) {
		t.Fatal("original bytes changed")
	}
	if _, err := os.Stat(original + ".hls-cache/terminal.json"); err != nil {
		t.Fatal("original checkpoint changed")
	}
	if _, err := os.Stat(task.Meta.SingleFilepath() + ".reservation.json"); err != nil {
		t.Fatal("revision reservation missing")
	}
	again, err := d.PrepareRecordedTerminalRevision(task.ID, "original-candidate", resource, fileID, partial, manifest, recordedTestResourceHash(), "fresh-alias")
	if err != nil || again != result {
		t.Fatal("untouched exact reservation was not reconciled")
	}
	if _, err := d.PrepareRecordedTerminalRevision(task.ID, "original-candidate", resource, fileID, partial, manifest, recordedTestResourceHash(), "different-alias"); err == nil {
		t.Fatal("different alias replaced exact reservation")
	}
	if err := os.WriteFile(task.Meta.SingleFilepath()+".recorded-started", []byte(result.Revision), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := d.PrepareRecordedTerminalRevision(task.ID, "original-candidate", resource, fileID, partial, manifest, recordedTestResourceHash(), "fresh-alias"); err == nil {
		t.Fatal("consumed resume was prepared again")
	}
}

func TestRecordedTerminalPlanRejectsSymlinkAndChangedCheckpoint(t *testing.T) {
	for _, mode := range []string{"media-symlink", "terminal-symlink", "wrong-terminal", "wrong-segments", "wrong-binding"} {
		t.Run(mode, func(t *testing.T) {
			task, partial, manifest := recordedTerminalFixture(t)
			resource, fileID := task.Meta.Req.Labels["recorded_resource_id"], task.Meta.Req.Labels["recorded_media_file_id"]
			name := task.Meta.SingleFilepath()
			if mode == "media-symlink" {
				if err := os.Rename(name, name+".saved"); err != nil {
					t.Fatal(err)
				}
				if err := os.Symlink(name+".saved", name); err != nil {
					t.Fatal(err)
				}
			}
			terminal := filepath.Join(name+".hls-cache", "terminal.json")
			if mode == "terminal-symlink" {
				if err := os.Rename(terminal, terminal+".saved"); err != nil {
					t.Fatal(err)
				}
				if err := os.Symlink(terminal+".saved", terminal); err != nil {
					t.Fatal(err)
				}
			}
			if mode == "wrong-terminal" {
				if err := os.WriteFile(terminal, []byte(`{"status":500}`), 0600); err != nil {
					t.Fatal(err)
				}
			}
			if mode == "wrong-segments" {
				task.Meta.Req.Labels["checkpoint_segments"] = "3"
			}
			if mode == "wrong-binding" {
				path := filepath.Join(name+".hls-cache", "binding.json")
				if err := os.WriteFile(path, []byte(`{"Binding":"`+strings.Repeat("c", 64)+`","Manifest":"`+manifest+`","Segments":2}`), 0600); err != nil {
					t.Fatal(err)
				}
			}
			if _, err := recordedTerminalPlan(task, "original-candidate", resource, fileID, partial, manifest, recordedTestResourceHash(), "fresh-alias"); err == nil {
				t.Fatal("changed checkpoint accepted")
			}
		})
	}
}

func TestRecordedTerminalStartNeverPausesOtherTasksOrRepeats(t *testing.T) {
	task, partial, manifest := recordedTerminalFixture(t)
	task.ID = "recorded-terminal-start-task"
	d := NewDownloader(&DownloaderConfig{StorageDir: t.TempDir()})
	if err := d.storage.Setup([]string{bucketTask, bucketSave, bucketConfig}); err != nil {
		t.Fatal(err)
	}
	defer d.storage.Close()
	d.tasks = []*Task{task}
	resource, fileID := task.Meta.Req.Labels["recorded_resource_id"], task.Meta.Req.Labels["recorded_media_file_id"]
	receipt, err := d.PrepareRecordedTerminalRevision(task.ID, "original-candidate", resource, fileID, partial, manifest, recordedTestResourceHash(), "fresh-alias")
	if err != nil {
		t.Fatal(err)
	}
	other, _ := repairTaskFixture(t)
	other.ID = "unrelated"
	other.Status = base.DownloadStatusRunning
	d.tasks = append(d.tasks, other)
	called := 0
	start := func(*Task) error { called++; return nil }
	if err := d.startRecordedTerminalRevision(task.ID, receipt.Revision, start); err == nil || called != 0 || other.Status != base.DownloadStatusRunning {
		t.Fatal("active unrelated task was disturbed")
	}
	other.Status = base.DownloadStatusPause
	if err := d.startRecordedTerminalRevision(task.ID, strings.Repeat("0", 64), start); err == nil || called != 0 {
		t.Fatal("wrong revision started")
	}
	if err := os.WriteFile(task.Meta.SingleFilepath()+".recorded-started", []byte(receipt.Revision), 0600); err != nil {
		t.Fatal(err)
	}
	if err := d.startRecordedTerminalRevision(task.ID, receipt.Revision, start); err == nil || called != 0 {
		t.Fatal("already claimed resume started")
	}
	if err := os.Remove(task.Meta.SingleFilepath() + ".recorded-started"); err != nil {
		t.Fatal(err)
	}
	if err := d.startRecordedTerminalRevision(task.ID, receipt.Revision, start); err != nil || called != 1 || other.Status != base.DownloadStatusPause {
		t.Fatal("exact paused revision not started")
	}
}

func TestConcurrentRecordedPreparationAndStartDoNotDuplicateEffects(t *testing.T) {
	task, partial, manifest := recordedTerminalFixture(t)
	task.ID = "recorded-concurrent-task"
	d := NewDownloader(&DownloaderConfig{StorageDir: t.TempDir()})
	if err := d.storage.Setup([]string{bucketTask, bucketSave, bucketConfig}); err != nil {
		t.Fatal(err)
	}
	defer d.storage.Close()
	d.tasks = []*Task{task}
	resource, fileID := task.Meta.Req.Labels["recorded_resource_id"], task.Meta.Req.Labels["recorded_media_file_id"]
	var wg sync.WaitGroup
	plans := make(chan StreamRepairReceipt, 2)
	errors := make(chan error, 2)
	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			p, e := d.PrepareRecordedTerminalRevision(task.ID, "original-candidate", resource, fileID, partial, manifest, recordedTestResourceHash(), "fresh-alias")
			plans <- p
			errors <- e
		}()
	}
	wg.Wait()
	close(plans)
	close(errors)
	for e := range errors {
		if e != nil {
			t.Fatal(e)
		}
	}
	first := <-plans
	second := <-plans
	if first != second {
		t.Fatal("concurrent preparation changed revision")
	}
	var count atomic.Int32
	starts := make(chan error, 2)
	start := func(task *Task) error {
		count.Add(1)
		task.statusLock.Lock()
		task.updateStatus(base.DownloadStatusRunning)
		task.statusLock.Unlock()
		return nil
	}
	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func() { defer wg.Done(); starts <- d.startRecordedTerminalRevision(task.ID, first.Revision, start) }()
	}
	wg.Wait()
	close(starts)
	failures := 0
	for e := range starts {
		if e != nil {
			failures++
		}
	}
	if count.Load() != 1 || failures != 1 {
		t.Fatal("concurrent start was not exact-once")
	}
}
