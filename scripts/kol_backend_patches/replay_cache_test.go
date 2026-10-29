package stream

import (
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
)

func cacheGet(t *testing.T, c *replayCache, index int) (int, []byte) {
	t.Helper()
	key := ""
	i := 0
	for _, line := range strings.Split(string(c.playlist), "\n") {
		if line != "" && !strings.HasPrefix(line, "#") {
			if i == index {
				key = line
				break
			}
			i++
		}
	}
	response, err := http.Get("http://" + c.listener.Addr().String() + key)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	return response.StatusCode, body
}
func TestReplayCacheRestartRetainsVerifiedSegments(t *testing.T) {
	var first, second atomic.Int32
	origin := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/replay.m3u8":
			fmt.Fprint(w, "#EXTM3U\n#EXTINF:5,\nfirst.ts?ticket=private\n#EXTINF:5,\nsecond.ts\n#EXT-X-ENDLIST\n")
		case "/first.ts":
			first.Add(1)
			fmt.Fprint(w, "first verified segment")
		case "/second.ts":
			second.Add(1)
			fmt.Fprint(w, "second verified segment")
		}
	}))
	defer origin.Close()
	root := t.TempDir()
	c, err := newReplayCache(origin.URL+"/replay.m3u8", map[string]string{"Cookie": "private"}, root, "original-task")
	if err != nil {
		t.Fatal(err)
	}
	status, body := cacheGet(t, c, 0)
	if status != 200 || string(body) != "first verified segment" || c.Complete() {
		t.Fatal("first checkpoint invalid")
	}
	c.Close()
	c, err = newReplayCache(origin.URL+"/replay.m3u8", map[string]string{"Cookie": "private"}, root, "original-task")
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	status, body = cacheGet(t, c, 0)
	if status != 200 || string(body) != "first verified segment" || first.Load() != 1 {
		t.Fatal("verified segment downloaded again")
	}
	status, _ = cacheGet(t, c, 1)
	if status != 200 || !c.Complete() || second.Load() != 1 {
		t.Fatal("original segment set not complete")
	}
	_ = filepath.Walk(root, func(name string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && strings.HasSuffix(name, ".json") {
			data, _ := os.ReadFile(name)
			if strings.Contains(string(data), "private") || strings.Contains(string(data), origin.URL) {
				t.Error("checkpoint metadata leaked credential")
			}
		}
		return err
	})
}
func TestReplayCacheIncompleteBodyCannotCommit(t *testing.T) {
	var calls atomic.Int32
	var broken atomic.Bool
	broken.Store(true)
	origin := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, ".m3u8") {
			fmt.Fprint(w, "#EXTM3U\n#EXTINF:5,\np.ts\n#EXT-X-ENDLIST\n")
			return
		}
		calls.Add(1)
		if broken.Load() {
			w.Header().Set("Content-Length", "20")
			fmt.Fprint(w, "cut")
			return
		}
		fmt.Fprint(w, "complete segment")
	}))
	defer origin.Close()
	root := t.TempDir()
	c, err := newReplayCache(origin.URL+"/replay.m3u8", nil, root, "task")
	if err != nil {
		t.Fatal(err)
	}
	status, _ := cacheGet(t, c, 0)
	if status != 502 || c.Complete() || calls.Load() != 3 {
		t.Fatal("incomplete body accepted or unbounded retry")
	}
	c.Close()
	broken.Store(false)
	c, err = newReplayCache(origin.URL+"/replay.m3u8", nil, root, "task")
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	status, body := cacheGet(t, c, 0)
	if status != 200 || string(body) != "complete segment" || !c.Complete() {
		t.Fatal("same checkpoint recovery failed")
	}
}
func TestReplayCacheRejectsMutationAndAuthRetry(t *testing.T) {
	for _, mode := range []string{"manifest", "corruption", "proof_corruption", "authentication"} {
		t.Run(mode, func(t *testing.T) {
			var changed atomic.Bool
			var calls atomic.Int32
			origin := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if strings.HasSuffix(r.URL.Path, ".m3u8") {
					duration := 5
					if changed.Load() && mode == "manifest" {
						duration = 6
					}
					fmt.Fprintf(w, "#EXTM3U\n#EXTINF:%d,\np.ts\n#EXT-X-ENDLIST\n", duration)
					return
				}
				calls.Add(1)
				if mode == "authentication" {
					w.WriteHeader(403)
					return
				}
				fmt.Fprint(w, "verified bytes")
			}))
			defer origin.Close()
			root := t.TempDir()
			c, err := newReplayCache(origin.URL+"/replay.m3u8", nil, root, "task")
			if err != nil {
				t.Fatal(err)
			}
			status, _ := cacheGet(t, c, 0)
			if mode == "authentication" {
				defer c.Close()
				if status != 403 || calls.Load() != 1 || c.Complete() {
					t.Fatal("authentication retried or accepted")
				}
				again, _ := cacheGet(t, c, 0)
				if again != 403 || calls.Load() != 1 {
					t.Fatal("terminal authentication failure was retried")
				}
				c.Close()
				if againCache, e := newReplayCache(origin.URL+"/replay.m3u8", nil, root, "task"); e == nil {
					againCache.Close()
					t.Fatal("terminal auth restart accepted")
				}
				if calls.Load() != 1 {
					t.Fatal("terminal auth restart fetched origin")
				}
				return
			}
			if status != 200 {
				t.Fatal("fixture failed")
			}
			c.Close()
			changed.Store(true)
			if mode == "proof_corruption" {
				files, _ := filepath.Glob(filepath.Join(root, "*.bin.json"))
				_ = os.WriteFile(files[0], []byte("bad json"), 0600)
			}
			if mode == "corruption" {
				files, _ := filepath.Glob(filepath.Join(root, "*.bin"))
				if len(files) != 1 {
					t.Fatal("missing checkpoint")
				}
				_ = os.WriteFile(files[0], []byte("tampered"), 0600)
			}
			c, err = newReplayCache(origin.URL+"/replay.m3u8", nil, root, "task")
			if mode == "manifest" {
				if err == nil {
					c.Close()
					t.Fatal("changed manifest accepted")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			defer c.Close()
			status, _ = cacheGet(t, c, 0)
			if status != 502 || c.Complete() || calls.Load() != 1 {
				t.Fatal("corrupt cache reused or silently redownloaded")
			}
		})
	}
}
func TestReplayCacheRejectsForeignSchemeOrUnendedPlaylist(t *testing.T) {
	for _, body := range []string{"#EXTM3U\n#EXTINF:5,\na.ts\n", "#EXTM3U\n#EXTINF:5,\nfile:///private/data\n#EXT-X-ENDLIST\n", "#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI=\"file:///private/key\"\n#EXTINF:5,\na.ts\n#EXT-X-ENDLIST\n"} {
		origin := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { fmt.Fprint(w, body) }))
		c, err := newReplayCache(origin.URL+"/replay.m3u8", nil, t.TempDir(), "task")
		origin.Close()
		if err == nil {
			c.Close()
			t.Fatal("invalid checkpoint origin accepted")
		}
	}
}

func TestReplayCacheRejectsCrossOriginResourcesAndRedirects(t *testing.T) {
	var foreignCalls atomic.Int32
	foreign := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { foreignCalls.Add(1); fmt.Fprint(w, "must not fetch") }))
	defer foreign.Close()
	for _, mode := range []string{"resource", "redirect"} {
		t.Run(mode, func(t *testing.T) {
			source := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if mode == "redirect" {
					http.Redirect(w, r, foreign.URL+"/other.m3u8", 302)
					return
				}
				fmt.Fprintf(w, "#EXTM3U\n#EXTINF:5,\n%s/private.ts\n#EXT-X-ENDLIST\n", foreign.URL)
			}))
			defer source.Close()
			c, err := newReplayCache(source.URL+"/source.m3u8", map[string]string{"Authorization": "private"}, t.TempDir(), "same-task")
			if err == nil {
				c.Close()
				t.Fatal("cross-origin transport accepted")
			}
			if foreignCalls.Load() != 0 {
				t.Fatal("credentials or request reached foreign target")
			}
		})
	}
}
func TestReplayCacheBindsEffectiveRedirectDirectory(t *testing.T) {
	var wrong atomic.Int32
	source := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/start.m3u8" {
			http.Redirect(w, r, "/effective/source.m3u8", 302)
			return
		}
		if strings.HasSuffix(r.URL.Path, ".m3u8") {
			fmt.Fprint(w, "#EXTM3U\n#EXTINF:5,\np.ts\n#EXT-X-ENDLIST\n")
			return
		}
		if r.URL.Path != "/effective/p.ts" {
			wrong.Add(1)
			http.NotFound(w, r)
			return
		}
		fmt.Fprint(w, "correct directory")
	}))
	defer source.Close()
	c, err := newReplayCache(source.URL+"/start.m3u8", nil, t.TempDir(), "same-task")
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	status, body := cacheGet(t, c, 0)
	if status != 200 || string(body) != "correct directory" || wrong.Load() != 0 {
		t.Fatal("relative URI used the pre-redirect directory")
	}
}
func TestReplayReservationRejectsForeignOccupiedOutput(t *testing.T) {
	name := filepath.Join(t.TempDir(), "target-compressed (1).mp4")
	labels := map[string]string{"media_repair_revision": "revision", "media_repair_previous_sha256": "old-hash", "media_repair_task_id": "same-task", "capture_id": "candidate", "live_id": "live"}
	marker := map[string]string{"revision": "revision", "previous_sha256": "old-hash", "task_id": "same-task", "candidate_id": "candidate", "live_id": "live"}
	if err := writeReplayJSON(name+".reservation.json", marker); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(name, nil, 0600); err != nil {
		t.Fatal(err)
	}
	if err := validateReplayReservation(name, labels); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(name, []byte("foreign artifact"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := validateReplayReservation(name, labels); err == nil {
		t.Fatal("occupied path could be overwritten")
	}
}

func TestReplayManifestAuthTerminalDoesNotRefetch(t *testing.T) {
	var calls atomic.Int32
	origin := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls.Add(1); w.WriteHeader(403) }))
	defer origin.Close()
	root := t.TempDir()
	for i := 0; i < 2; i++ {
		c, err := newReplayCache(origin.URL+"/replay.m3u8", nil, root, "same-task")
		if err == nil {
			c.Close()
			t.Fatal("auth accepted")
		}
	}
	if calls.Load() != 1 {
		t.Fatal("terminal manifest authentication retried")
	}
}

func TestObservedXiaoetongCrossOriginSegments(t *testing.T) {
	origin, _ := url.Parse("https://live-ex-speed.xiaoeknow.com/replay.m3u8")
	for _, test := range []struct {
		target  string
		headers map[string]string
		allowed bool
	}{
		{"https://encrypt-k-vod.xet.tech/part.ts", nil, true},
		{"https://encrypt-k-vod.xet.tech/part.ts?provider=issued", nil, true},
		{"https://encrypt-k-vod.xet.tech/part.ts#fragment", nil, false},
		{"https://encrypt-k-vod.xet.tech/part.ts", map[string]string{"Cookie": "private"}, false},
		{"https://encrypt-k-vod.xet.tech.evil.test/part.ts", nil, false},
		{"http://encrypt-k-vod.xet.tech/part.ts", nil, false},
		{"https://encrypt-k-vod.xet.tech:444/part.ts", nil, false},
		{"https://127.0.0.1/part.ts", nil, false},
	} {
		target, _ := url.Parse(test.target)
		if allowedReplayResource(origin, target, test.headers) != test.allowed {
			t.Fatal(test.target)
		}
	}
	origin.RawQuery = "ticket=private"
	if allowedReplayResource(origin, origin.ResolveReference(&url.URL{Scheme: "https", Host: "encrypt-k-vod.xet.tech", Path: "/part.ts"}), nil) {
		t.Fatal("signed origin")
	}
	other, _ := url.Parse("https://other.test/replay.m3u8")
	target, _ := url.Parse("https://encrypt-k-vod.xet.tech/part.ts")
	if allowedReplayResource(other, target, nil) {
		t.Fatal("unverified origin")
	}
}
