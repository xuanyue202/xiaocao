package stream

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/GopeedLab/gopeed/internal/fetcher"
	"github.com/GopeedLab/gopeed/pkg/base"
	fstream "github.com/GopeedLab/gopeed/pkg/protocol/stream"
)

func TestFiniteReplayFFmpegRestartReusesSegmentsAndRejectsSkip(t *testing.T) {
	ffmpeg, err := exec.LookPath("ffmpeg")
	if err != nil {
		t.Skip("ffmpeg unavailable")
	}
	if _, err = exec.LookPath("ffprobe"); err != nil {
		t.Skip("ffprobe unavailable")
	}
	source := t.TempDir()
	playlist := filepath.Join(source, "source.m3u8")
	args := []string{"-v", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10", "-f", "lavfi", "-i", "sine=frequency=600:sample_rate=44100", "-t", "8", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-g", "20", "-sc_threshold", "0", "-c:a", "aac", "-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod", "-hls_segment_filename", filepath.Join(source, "seg%02d.ts"), playlist}
	if output, e := exec.Command(ffmpeg, args...).CombinedOutput(); e != nil {
		t.Fatalf("fixture generation: %v %s", e, output)
	}
	var broken atomic.Bool
	broken.Store(true)
	var mu sync.Mutex
	counts := map[string]int{}
	origin := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		name := filepath.Base(r.URL.Path)
		if strings.HasSuffix(name, ".ts") {
			mu.Lock()
			counts[name]++
			mu.Unlock()
		}
		if name == "seg01.ts" && broken.Load() {
			w.Header().Set("Content-Length", "10000")
			fmt.Fprint(w, "cut")
			return
		}
		if name == "seg01.ts" && !broken.Load() {
			time.Sleep(21 * time.Second)
		}
		http.ServeFile(w, r, filepath.Join(source, name))
	}))
	defer origin.Close()
	root := t.TempDir()
	name := "target-compressed.mp4"
	build := func() *Fetcher {
		return &Fetcher{config: &config{FfmpegPath: ffmpeg}, doneCh: make(chan error, 1), meta: &fetcher.FetcherMeta{
			Req: &base.Request{URL: origin.URL + "/source.m3u8", Labels: map[string]string{"capture_id": "same-candidate", "live_id": "same-live", "hls_finite": "true", "hls_duration_sec": "8"}, Extra: &fstream.ReqExtra{Compress: true}},
			Res: &base.Resource{Files: []*base.FileInfo{{Name: name}}}, Opts: &base.Options{Path: root, Name: name, Extra: &fstream.OptsExtra{Compress: true}},
		}}
	}
	wait := func(f *Fetcher) error {
		if e := f.Start(); e != nil {
			return e
		}
		select {
		case e := <-f.doneCh:
			return e
		case <-time.After(30 * time.Second):
			f.Close()
			t.Fatal("finite fixture timed out")
			return nil
		}
	}
	first := build()
	if err = wait(first); err == nil {
		t.Fatal("skipped HLS segment reported complete")
	}
	mu.Lock()
	prior := counts["seg00.ts"]
	mu.Unlock()
	if prior != 1 {
		t.Fatalf("first verified segment fetches=%d", prior)
	}
	if _, err = os.Stat(filepath.Join(root, name+".hls-cache")); err != nil {
		t.Fatal("failed replay checkpoint missing")
	}
	broken.Store(false)
	second := build()
	if err = wait(second); err != nil {
		t.Fatalf("original checkpoint resume: %v", err)
	}
	mu.Lock()
	after := counts["seg00.ts"]
	mu.Unlock()
	if after != prior {
		t.Fatal("resume redownloaded a verified segment")
	}
	if second.meta.Req.Labels["checkpoint_integrity_verified"] != "true" {
		t.Fatal("complete coverage not bound to task")
	}
	if _, err = os.Stat(filepath.Join(root, name+".hls-cache")); !os.IsNotExist(err) {
		t.Fatal("completed replay retained raw segment cache")
	}
}

// The child exits while FFmpeg is active; no completion defer can write labels.
func TestReplayCheckpointAbruptProcessExit(t *testing.T) {
	if os.Getenv("KOL_CHECKPOINT_CHILD") == "1" {
		root := os.Getenv("KOL_CHECKPOINT_ROOT")
		meta := &fetcher.FetcherMeta{Req: &base.Request{URL: os.Getenv("KOL_CHECKPOINT_URL"), Labels: map[string]string{"capture_id": "same-candidate", "live_id": "same-live", "hls_finite": "true", "hls_duration_sec": "8"}, Extra: &fstream.ReqExtra{Compress: true}}, Res: &base.Resource{Files: []*base.FileInfo{{Name: "target-compressed.mp4"}}}, Opts: &base.Options{Path: root, Name: "target-compressed.mp4", Extra: &fstream.OptsExtra{Compress: true}}}
		f := &Fetcher{config: &config{FfmpegPath: "ffmpeg"}, doneCh: make(chan error, 1), meta: meta}
		if err := f.Start(); err != nil {
			t.Fatal(err)
		}
		// Simulate Downloader.saveTask immediately after Start returns.
		data, _ := json.Marshal(meta.Req.Labels)
		_ = os.WriteFile(filepath.Join(root, "task-labels.json"), data, 0600)
		for i := 0; i < 500; i++ {
			files, _ := filepath.Glob(filepath.Join(root, "target-compressed.mp4.hls-cache", "*.bin.json"))
			if len(files) > 0 {
				os.Exit(17)
			}
			time.Sleep(10 * time.Millisecond)
		}
		t.Fatal("child checkpoint timeout")
		return
	}
	if _, err := exec.LookPath("ffmpeg"); err != nil {
		t.Skip("ffmpeg unavailable")
	}
	source := t.TempDir()
	args := []string{"-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10", "-t", "8", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-g", "20", "-sc_threshold", "0", "-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod", "-hls_segment_filename", filepath.Join(source, "seg%02d.ts"), filepath.Join(source, "source.m3u8")}
	if data, err := exec.Command("ffmpeg", args...).CombinedOutput(); err != nil {
		t.Fatalf("fixture: %v %s", err, data)
	}
	var blocked atomic.Bool
	blocked.Store(true)
	var first atomic.Int32
	origin := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		name := filepath.Base(r.URL.Path)
		if name == "seg00.ts" {
			first.Add(1)
		}
		if name == "seg01.ts" && blocked.Load() {
			select {
			case <-r.Context().Done():
				return
			case <-time.After(10 * time.Second):
				return
			}
		}
		http.ServeFile(w, r, filepath.Join(source, name))
	}))
	defer origin.Close()
	root := t.TempDir()
	cmd := exec.Command(os.Args[0], "-test.run=^TestReplayCheckpointAbruptProcessExit$")
	cmd.Env = append(os.Environ(), "KOL_CHECKPOINT_CHILD=1", "KOL_CHECKPOINT_ROOT="+root, "KOL_CHECKPOINT_URL="+origin.URL+"/source.m3u8")
	if err := cmd.Run(); err == nil {
		t.Fatal("expected abrupt child exit")
	}
	data, err := os.ReadFile(filepath.Join(root, "task-labels.json"))
	if err != nil {
		t.Fatal(err)
	}
	var labels map[string]string
	if json.Unmarshal(data, &labels) != nil || labels["checkpoint_basis"] != "verified_hls_segments" {
		t.Fatal("checkpoint binding not persisted before exit")
	}
	prior := first.Load()
	if prior != 1 {
		t.Fatalf("verified segment requests %d", prior)
	}
	blocked.Store(false)
	f := &Fetcher{config: &config{FfmpegPath: "ffmpeg"}, doneCh: make(chan error, 1), meta: &fetcher.FetcherMeta{Req: &base.Request{URL: origin.URL + "/source.m3u8", Labels: labels, Extra: &fstream.ReqExtra{Compress: true}}, Res: &base.Resource{Files: []*base.FileInfo{{Name: "target-compressed.mp4"}}}, Opts: &base.Options{Path: root, Name: "target-compressed.mp4", Extra: &fstream.OptsExtra{Compress: true}}}}
	if err := f.Start(); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-f.doneCh:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(30 * time.Second):
		f.Close()
		t.Fatal("resume timeout")
	}
	if first.Load() != prior {
		t.Fatal("abrupt restart downloaded verified segment again")
	}
}
