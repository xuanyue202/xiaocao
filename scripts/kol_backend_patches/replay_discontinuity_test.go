package stream

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/GopeedLab/gopeed/internal/fetcher"
	"github.com/GopeedLab/gopeed/pkg/base"
	fstream "github.com/GopeedLab/gopeed/pkg/protocol/stream"
)

func TestReplayPeriodsPreserveDeclaredBoundaryAndKeyState(t *testing.T) {
	lines := strings.Split("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:5\n#EXT-X-MEDIA-SEQUENCE:20\n#EXT-X-KEY:METHOD=AES-128,URI=\"/local/key\"\n#EXT-X-MAP:URI=\"/local/init\"\n#EXTINF:3,\n/local/a.ts\n#EXT-X-DISCONTINUITY\n#EXTINF:4,\n/local/b.ts\n#EXT-X-ENDLIST", "\n")
	periods, durations, err := replayPeriods(lines)
	if err != nil || len(periods) != 2 || durations[0] != 3 || durations[1] != 4 {
		t.Fatalf("periods: %v %v", durations, err)
	}
	for i, body := range periods {
		text := string(body)
		if !strings.Contains(text, fmt.Sprintf("#EXT-X-MEDIA-SEQUENCE:%d", 20+i)) || !strings.Contains(text, "URI=\"/local/key\"") || !strings.Contains(text, "URI=\"/local/init\"") || !strings.HasSuffix(text, "#EXT-X-ENDLIST\n") {
			t.Fatalf("state lost in period %d", i)
		}
	}
	if strings.Contains(string(periods[0]), "/local/b.ts") || strings.Contains(string(periods[1]), "/local/a.ts") {
		t.Fatal("periods overlap")
	}
	if _, _, err = replayPeriods([]string{"#EXTM3U", "#EXTINF:3,", "#EXT-X-DISCONTINUITY", "/local/a.ts"}); err == nil {
		t.Fatal("incomplete segment accepted")
	}
}

func TestReplayFFmpegDeclaredDiscontinuityKeepsAllSegments(t *testing.T) {
	ffmpeg, err := exec.LookPath("ffmpeg")
	if err != nil {
		t.Skip("ffmpeg unavailable")
	}
	if _, err = exec.LookPath("ffprobe"); err != nil {
		t.Skip("ffprobe unavailable")
	}
	source := t.TempDir()
	for i := 0; i < 2; i++ {
		output := filepath.Join(source, fmt.Sprintf("period%d.ts", i))
		args := []string{"-v", "error", "-f", "lavfi", "-i", fmt.Sprintf("color=c=%s:size=64x64:rate=10", []string{"red", "blue"}[i]), "-t", "2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-f", "mpegts", output}
		if out, e := exec.Command(ffmpeg, args...).CombinedOutput(); e != nil {
			t.Fatalf("fixture: %v %s", e, out)
		}
	}
	body := "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:2,\nperiod0.ts\n#EXT-X-DISCONTINUITY\n#EXTINF:2,\nperiod1.ts\n#EXT-X-ENDLIST\n"
	origin := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/source.m3u8" {
			fmt.Fprint(w, body)
			return
		}
		http.ServeFile(w, r, filepath.Join(source, filepath.Base(r.URL.Path)))
	}))
	defer origin.Close()
	root := t.TempDir()
	name := "discontinuity-compressed.mp4"
	f := &Fetcher{config: &config{FfmpegPath: ffmpeg}, doneCh: make(chan error, 1), meta: &fetcher.FetcherMeta{
		Req: &base.Request{URL: origin.URL + "/source.m3u8", Labels: map[string]string{"capture_id": "original", "live_id": "same-live", "hls_finite": "true", "hls_duration_sec": "4"}, Extra: &fstream.ReqExtra{Compress: true}},
		Res: &base.Resource{Files: []*base.FileInfo{{Name: name}}}, Opts: &base.Options{Path: root, Name: name, Extra: &fstream.OptsExtra{Compress: true}}}}
	if err = f.Start(); err != nil {
		t.Fatal(err)
	}
	select {
	case err = <-f.doneCh:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(20 * time.Second):
		f.Close()
		t.Fatal("discontinuity replay timeout")
	}
	if f.meta.Req.Labels["checkpoint_segments"] != "2" || f.meta.Req.Labels["checkpoint_integrity_verified"] != "true" {
		t.Fatal("full segment acceptance missing")
	}
	if out, e := exec.Command(ffmpeg, "-v", "error", "-xerror", "-i", filepath.Join(root, name), "-f", "null", "-").CombinedOutput(); e != nil || len(out) != 0 {
		t.Fatalf("full decode: %v %s", e, out)
	}
	if _, e := os.Stat(filepath.Join(root, name+".hls-cache")); !os.IsNotExist(e) {
		t.Fatal("complete source cache retained")
	}
}

func TestReplayPeriodsPreserveMapKeyAfterSegmentKeyRotation(t *testing.T) {
	lines := strings.Split("#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI=\"/key-a\",IV=0x01\n#EXT-X-MAP:URI=\"/init\"\n#EXT-X-KEY:METHOD=AES-128,URI=\"/key-b\"\n#EXTINF:2,\n/a.ts\n#EXT-X-DISCONTINUITY\n#EXTINF:3,\n/b.ts\n#EXT-X-ENDLIST", "\n")
	periods, _, err := replayPeriods(lines)
	if err != nil || len(periods) != 2 {
		t.Fatalf("periods: %v", err)
	}
	text := string(periods[1])
	a, init, b := strings.Index(text, "URI=\"/key-a\""), strings.Index(text, "#EXT-X-MAP:"), strings.Index(text, "URI=\"/key-b\"")
	if a < 0 || init <= a || b <= init {
		t.Fatal("init encryption key association changed")
	}
}
