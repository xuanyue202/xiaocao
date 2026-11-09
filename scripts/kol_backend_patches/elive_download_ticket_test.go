package api

import (
	"encoding/json"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"wx_channel/internal/livecapture"
)

func TestRecordedCourseRequiresExactFileAndObservedFinitePlaylist(t *testing.T) {
	for _, invalid := range []string{"", "no_type", "no_live_context", "retained_candidate", "ticket_alias", "wrong_alias", "stale_alias", "missing_alias", "stale_response", "future_response", "event_stream", "short_file", "wrong_file", "wrong_source", "no_end", "missing_resource", "wrong_path"} {
		t.Run(invalid, func(t *testing.T) {
			root := t.TempDir()
			dir := filepath.Join(root, "elive_live_debug", "m3u8")
			os.MkdirAll(dir, 0700)
			resource := "https://encrypt-k-vod.xet.tech/account/c700e05f5001834826931137742/drm/v.f421220.m3u8"
			c := eliveLiveCandidate{ID: "recorded-" + invalid, LiveID: "l_observed_room", URL: resource,
				Captured: time.Now().Format("2006-01-02 15:04:05"), MediaType: "m3u8",
				SourceURL:  "https://appsnm3rlcp3566.h5.xiaoeknow.com/xe.material-center.play/getPlayUrl",
				SourcePath: "/xe.material-center.play/getPlayUrl"}
			if invalid == "no_live_context" {
				c.LiveID = ""
			}
			if invalid == "retained_candidate" || invalid == "stale_response" {
				c.Captured = time.Now().Add(-34 * time.Minute).Format("2006-01-02 15:04:05")
			}
			if invalid == "wrong_source" {
				c.SourceURL = "https://other.example/xe.material-center.play/getPlayUrl"
			}
			data, _ := json.Marshal(c)
			os.WriteFile(filepath.Join(root, "elive_live_debug", "candidates.jsonl"), append(data, '\n'), 0600)
			playlist := "#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:120,\nsegment.ts\n#EXT-X-ENDLIST\n"
			if invalid == "no_type" {
				playlist = strings.ReplaceAll(playlist, "#EXT-X-PLAYLIST-TYPE:VOD\n", "")
			}
			if invalid == "event_stream" {
				playlist = strings.ReplaceAll(playlist, "VOD", "EVENT")
			}
			if invalid == "no_end" {
				playlist = strings.ReplaceAll(playlist, "#EXT-X-ENDLIST\n", "")
			}
			path := filepath.Join(dir, "recorded.m3u8")
			os.WriteFile(path, []byte(playlist), 0600)
			at := time.Now()
			if invalid == "stale_response" {
				at = at.Add(-25 * time.Minute)
			}
			if invalid == "future_response" {
				at = at.Add(2 * time.Minute)
			}
			event, _ := json.Marshal(map[string]any{"kind": "response.body", "status": 200, "url": resource,
				"at": at.Format(time.RFC3339Nano), "file": path})
			os.WriteFile(filepath.Join(root, "elive_live_debug", "events.jsonl"), append(event, '\n'), 0600)
			extra := map[string]string{"type": "live_capture", "source": "xiaocao", "capture_id": c.ID,
				"live_id": c.LiveID, "recorded_resource_id": "v_6aeac14ce4b023c0863c984c", "recorded_media_file_id": "5001834826931137742"}
			aliasCase := strings.HasSuffix(invalid, "alias")
			if aliasCase {
				alias := c
				alias.ID = "fresh-ticket"
				alias.LiveID = ""
				if invalid == "wrong_alias" {
					alias.URL = strings.Replace(resource, "5001834826931137742", "5001834826931139999", 1)
				}
				if invalid == "stale_alias" {
					alias.Captured = time.Now().Add(-25 * time.Minute).Format("2006-01-02 15:04:05")
				}
				if invalid != "missing_alias" {
					f, _ := os.OpenFile(filepath.Join(root, "elive_live_debug", "candidates.jsonl"), os.O_APPEND|os.O_WRONLY, 0600)
					b, _ := json.Marshal(alias)
					f.Write(append(b, '\n'))
					f.Close()
					livecapture.RememberCandidateURL(alias.ID, alias.URL+"?sign=fresh")
				}
				extra["recorded_ticket_candidate_id"] = alias.ID
			}
			if invalid == "wrong_file" {
				extra["recorded_media_file_id"] = "1234567890"
			}
			if invalid == "short_file" {
				extra["recorded_media_file_id"] = "1834826931137742"
			}
			if invalid == "missing_resource" {
				delete(extra, "recorded_resource_id")
			}
			raw := resource + "?sign=private&t=ffffffff"
			if !aliasCase {
				livecapture.RememberCandidateURL(c.ID, raw)
			} else {
				raw = resource + "?sign=fresh"
			}
			body := DownloadTaskPayload{URL: resource, Extra: extra}
			if invalid == "wrong_path" {
				body.URL = "https://encrypt-k-vod.xet.tech/another/drm/v.f421220.m3u8"
			}
			err := resolveXiaocaoCaptureDownload(&body, root)
			if invalid != "" && invalid != "no_type" && invalid != "retained_candidate" && invalid != "ticket_alias" && invalid != "no_live_context" {
				if err == nil {
					t.Fatal("unbound recording accepted")
				}
				return
			}
			if err != nil || body.URL != raw {
				t.Fatalf("exact recording rejected: %v", err)
			}
		})
	}
}

func TestRecordedCourseAllowsOnlyAuthorizedExactXedHost(t *testing.T) {
	for _, host := range []string{"t-vod.h5.xed.plus", "other.h5.xed.plus", "t-vod.h5.xed.plus.evil.test", "t-vod.h5.xed.plus:444"} {
		t.Run(host, func(t *testing.T) {
			root := t.TempDir()
			dir := filepath.Join(root, "elive_live_debug", "m3u8")
			os.MkdirAll(dir, 0700)
			resource := "https://" + host + "/account/c700e05f5001834826931137742/drm/v.f421220.m3u8"
			c := eliveLiveCandidate{ID: "recorded-xed", LiveID: "l_observed_room", URL: resource,
				Captured: time.Now().Format("2006-01-02 15:04:05"), MediaType: "m3u8",
				SourceURL:  "https://appsnm3rlcp3566.h5.xiaoeknow.com/xe.material-center.play/getPlayUrl",
				SourcePath: "/xe.material-center.play/getPlayUrl"}
			data, _ := json.Marshal(c)
			os.MkdirAll(filepath.Join(root, "elive_live_debug"), 0700)
			os.WriteFile(filepath.Join(root, "elive_live_debug", "candidates.jsonl"), append(data, '\n'), 0600)
			path := filepath.Join(dir, "recorded.m3u8")
			os.WriteFile(path, []byte("#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:120,\nsegment.ts\n#EXT-X-ENDLIST\n"), 0600)
			event, _ := json.Marshal(map[string]any{"kind": "response.body", "status": 200,
				"url": resource, "at": time.Now().Format(time.RFC3339Nano), "file": path})
			os.WriteFile(filepath.Join(root, "elive_live_debug", "events.jsonl"), append(event, '\n'), 0600)
			livecapture.RememberCandidateURL(c.ID, resource+"?sign=private")
			body := DownloadTaskPayload{URL: resource, Extra: map[string]string{
				"type": "live_capture", "source": "xiaocao", "capture_id": c.ID,
				"live_id": c.LiveID, "recorded_resource_id": "v_6aeac14ce4b023c0863c984c",
				"recorded_media_file_id": "5001834826931137742"}}
			err := resolveXiaocaoCaptureDownload(&body, root)
			if host == "t-vod.h5.xed.plus" {
				if err != nil {
					t.Fatalf("authorized exact host rejected: %v", err)
				}
			} else if err == nil {
				t.Fatal("unapproved xed host accepted")
			}
		})
	}
}

func TestXiaocaoCaptureDownloadResolvesTicketInsideSingleton(t *testing.T) {
	for _, invalid := range []string{"", "missing_ticket", "wrong_live", "wrong_path", "missing_candidate", "live_stream"} {
		t.Run(invalid, func(t *testing.T) {
			root := t.TempDir()
			id := "ticket-test-" + invalid
			resource := "https://encrypt-k-vod.xet.tech/content/playlist_eof.m3u8"
			if invalid == "live_stream" {
				resource = "https://encrypt-k-vod.xet.tech/content/liveplay.m3u8"
			}
			raw := resource + "?sign=private&t=ffffffff"
			if invalid != "missing_ticket" {
				livecapture.RememberCandidateURL(id, raw)
			}
			candidate := eliveLiveCandidate{ID: id, LiveID: "l_exact", MediaType: "m3u8", URL: resource}
			dir := filepath.Join(root, "elive_live_debug")
			if err := os.MkdirAll(dir, 0700); err != nil {
				t.Fatal(err)
			}
			data, err := json.Marshal(candidate)
			if err != nil {
				t.Fatal(err)
			}
			if invalid == "missing_candidate" {
				data = nil
			}
			if err := os.WriteFile(filepath.Join(dir, "candidates.jsonl"), append(data, '\n'), 0600); err != nil {
				t.Fatal(err)
			}
			body := DownloadTaskPayload{URL: resource, Extra: map[string]string{
				"type": "live_capture", "source": "xiaocao", "capture_id": id, "live_id": "l_exact",
			}}
			if invalid == "wrong_live" {
				body.Extra["live_id"] = "l_other"
			}
			if invalid == "wrong_path" {
				body.URL = "https://encrypt-k-vod.xet.tech/other/playlist_eof.m3u8"
			}
			err = resolveXiaocaoCaptureDownload(&body, root)
			if invalid != "" {
				if err == nil {
					t.Fatal("unbound candidate accepted")
				}
				if body.URL == raw {
					t.Fatal("failed validation exposed ticket")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if body.URL != raw {
				t.Fatal("download did not use singleton's exact ticket")
			}
			if livecapture.RedactSignedURL(body.URL) != resource {
				t.Fatal("public URL is not credential-free")
			}
		})
	}
}

func TestNumericNativeReplayRequiresObservedEndedPlaylist(t *testing.T) {
	for _, invalid := range []string{"", "late_response", "no_end", "not_vod", "wrong_resource", "old", "outside", "no_response"} {
		t.Run(invalid, func(t *testing.T) {
			root := t.TempDir()
			dir := filepath.Join(root, "elive_live_debug", "m3u8")
			os.MkdirAll(dir, 0700)
			resource := "https://live-ex-speed.xiaoeknow.com/5060_recording.m3u8"
			c := eliveLiveCandidate{ID: "numeric", Captured: time.Now().Format("2006-01-02 15:04:05"), SourceURL: "https://xet.kj1team.cn/_alive/v2/get_lookback_url", JSONPath: "data.miniAliveVideoUrl"}
			c.URL, c.LiveID, c.MediaType = resource, "l_exact", "m3u8"
			if invalid == "late_response" {
				c.Captured = time.Now().Add(-5 * time.Minute).Format("2006-01-02 15:04:05")
			}
			data, _ := json.Marshal(c)
			os.WriteFile(filepath.Join(root, "elive_live_debug", "candidates.jsonl"), append(data, '\n'), 0600)
			playlist := "#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:120,\nsegment.ts\n#EXT-X-ENDLIST\n"
			if invalid == "no_end" {
				playlist = strings.ReplaceAll(playlist, "#EXT-X-ENDLIST\n", "")
			}
			if invalid == "not_vod" {
				playlist = strings.ReplaceAll(playlist, "VOD", "EVENT")
			}
			path := filepath.Join(dir, "recording.m3u8")
			if invalid == "outside" {
				path = filepath.Join(root, "outside.m3u8")
			}
			os.WriteFile(path, []byte(playlist), 0600)
			at := time.Now()
			if invalid == "old" {
				at = at.Add(-time.Minute)
			}
			observed := resource
			if invalid == "wrong_resource" {
				observed += ".other"
			}
			event, _ := json.Marshal(map[string]any{"kind": "response.body", "status": 200, "url": observed, "at": at.Format(time.RFC3339Nano), "file": path})
			if invalid != "no_response" {
				os.WriteFile(filepath.Join(root, "elive_live_debug", "events.jsonl"), event, 0600)
			}
			u, _ := url.Parse(resource)
			valid := invalid == "" || invalid == "late_response"
			if got := hasObservedEndedNativePlaylist(root, c, u); got != valid {
				t.Fatalf("accepted=%v", got)
			}
			b := DownloadTaskPayload{URL: resource, Extra: map[string]string{"type": "live_capture", "source": "xiaocao", "capture_id": c.ID, "live_id": c.LiveID}}
			if e := resolveXiaocaoCaptureDownload(&b, root); (e == nil) != valid {
				t.Fatalf("restore accepted=%v", e == nil)
			}
		})
	}
}
