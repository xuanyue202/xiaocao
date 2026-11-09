package api

import (
	"bufio"
	"encoding/json"
	"fmt"
	"math"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"wx_channel/internal/livecapture"
)

// Resolve only inside the singleton: public candidate APIs deliberately omit
// signed queries. The caller supplies identity, never extracts the media ticket.
func resolveXiaocaoCaptureDownload(body *DownloadTaskPayload, rootDir string) error {
	if body.Extra["type"] != "live_capture" || body.Extra["source"] != "xiaocao" {
		return nil
	}
	id, liveID := body.Extra["capture_id"], body.Extra["live_id"]
	recorded := recordedResourceID.MatchString(body.Extra["recorded_resource_id"]) && recordedFileID.MatchString(body.Extra["recorded_media_file_id"])
	if id == "" || liveID == "" && !recorded {
		return fmt.Errorf("xiaocao capture identity is required")
	}
	items, err := loadEliveSourceJobCandidates(rootDir)
	if err != nil {
		return fmt.Errorf("xiaocao candidate evidence unavailable")
	}
	var selected *eliveLiveCandidate
	for i := range items {
		if items[i].ID == id {
			if selected != nil && (selected.LiveID != items[i].LiveID || selected.URL != items[i].URL) {
				return fmt.Errorf("xiaocao candidate identity is ambiguous")
			}
			selected = &items[i]
		}
	}
	if selected == nil || selected.LiveID != liveID || selected.MediaType != "m3u8" {
		return fmt.Errorf("xiaocao candidate live binding is invalid")
	}
	raw := livecapture.ResolveCandidateURL(id)
	if aliasID := body.Extra["recorded_ticket_candidate_id"]; aliasID != "" {
		var alias *eliveLiveCandidate
		for i := range items {
			if items[i].ID == aliasID {
				if alias != nil {
					return fmt.Errorf("xiaocao ticket alias ambiguous")
				}
				alias = &items[i]
			}
		}
		if alias == nil {
			return fmt.Errorf("xiaocao ticket alias missing")
		}
		ticket := livecapture.ResolveCandidateURL(aliasID)
		u, e := url.Parse(ticket)
		original, oe := url.Parse(selected.URL)
		at, ae := time.ParseInLocation("2006-01-02 15:04:05", alias.Captured, time.Local)
		if ticket == "" || e != nil || oe != nil || ae != nil || at.Before(time.Now().Add(-20*time.Minute)) || at.After(time.Now().Add(30*time.Second)) ||
			alias.MediaType != "m3u8" || alias.SourceURL != selected.SourceURL || alias.SourcePath != selected.SourcePath ||
			u.Scheme != original.Scheme || u.Host != original.Host || u.Path != original.Path ||
			!hasObservedEndedRecordedPlaylist(rootDir, *alias, u, body.Extra) {
			return fmt.Errorf("xiaocao ticket alias differs from exact recording")
		}
		raw = ticket
	}
	// This exact numeric recording is public and was returned by the native
	// merchant. Restore only a query-free resource with its saved ended-VOD
	// response. Encrypted/signed replay tickets must still stay memory-only.
	if raw == "" {
		public, e := url.Parse(selected.URL)
		if e == nil && public.RawQuery == "" && public.Fragment == "" && public.User == nil &&
			hasObservedEndedNativePlaylist(rootDir, *selected, public) {
			raw = selected.URL
		}
	}
	observed, observedErr := url.Parse(raw)
	requested, requestedErr := url.Parse(body.URL)
	if raw == "" || observedErr != nil || requestedErr != nil || observed.Scheme != "https" ||
		observed.User != nil || requested.User != nil || observed.Scheme != requested.Scheme ||
		observed.Host != requested.Host || observed.Path != requested.Path ||
		(liveID == "" && !hasObservedEndedRecordedPlaylist(rootDir, *selected, observed, body.Extra)) ||
		(!eliveFinitePlaylistName.MatchString(filepath.Base(observed.Path)) &&
			!hasObservedEndedNativePlaylist(rootDir, *selected, observed) &&
			!hasObservedEndedRecordedPlaylist(rootDir, *selected, observed, body.Extra)) {
		return fmt.Errorf("xiaocao fresh media ticket unavailable or mismatched")
	}
	body.URL = raw
	return nil
}

// Numeric recording names are accepted only from the singleton's actual HTTP
// response, not from a URL suffix or a merchant title.
func hasObservedEndedNativePlaylist(rootDir string, candidate eliveLiveCandidate, media *url.URL) bool {
	if media.Hostname() != "live-ex-speed.xiaoeknow.com" || !strings.HasSuffix(media.Path, ".m3u8") {
		return false
	}
	if candidate.SourceURL != "https://xet.kj1team.cn/_alive/v2/get_lookback_url" ||
		candidate.JSONPath != "data.miniAliveVideoUrl" && candidate.JSONPath != "data.aliveVideoUrl" {
		return false
	}
	return hasObservedFinitePlaylist(rootDir, candidate, media, true)
}

// Recorded-course recovery keeps the exact browser-issued ticket in memory.
// Its independent resource/file binding is verified by the capture coordinator;
// the singleton independently requires the actual finite playlist observation.
var recordedResourceID = regexp.MustCompile(`^v_[0-9a-f]{24}$`)
var recordedFileID = regexp.MustCompile(`^[0-9]{8,}$`)
var recordedPlaylistName = regexp.MustCompile(`^v\.f[0-9]+\.m3u8$`)
var recordedFileComponent = regexp.MustCompile(`^[0-9a-f]{8}([0-9]{8,})$`)

func recordedCourseMediaHost(host string) bool {
	return host == "encrypt-k-vod.xet.tech" || host == "t-vod.h5.xed.plus"
}

func hasObservedEndedRecordedPlaylist(rootDir string, candidate eliveLiveCandidate, media *url.URL, extra map[string]string) bool {
	if !recordedResourceID.MatchString(extra["recorded_resource_id"]) ||
		!recordedFileID.MatchString(extra["recorded_media_file_id"]) ||
		candidate.SourceURL != "https://appsnm3rlcp3566.h5.xiaoeknow.com/xe.material-center.play/getPlayUrl" ||
		candidate.SourcePath != "/xe.material-center.play/getPlayUrl" ||
		!recordedCourseMediaHost(media.Host) ||
		!recordedPlaylistName.MatchString(filepath.Base(media.Path)) {
		return false
	}
	matched := false
	for _, part := range strings.Split(media.Path, "/") {
		if match := recordedFileComponent.FindStringSubmatch(part); len(match) == 2 && match[1] == extra["recorded_media_file_id"] {
			matched = true
		}
	}
	return matched && hasObservedFinitePlaylist(rootDir, candidate, media, false)
}

func hasObservedFinitePlaylist(rootDir string, candidate eliveLiveCandidate, media *url.URL, requireVOD bool) bool {
	captured, err := time.ParseInLocation("2006-01-02 15:04:05", candidate.Captured, time.Local)
	if err != nil {
		return false
	}
	root, err := filepath.EvalSymlinks(filepath.Join(rootDir, "elive_live_debug", "m3u8"))
	if err != nil {
		return false
	}
	f, err := os.Open(filepath.Join(rootDir, "elive_live_debug", "events.jsonl"))
	if err != nil {
		return false
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 4096), 2*1024*1024)
	for scanner.Scan() {
		var event struct {
			Kind   string `json:"kind"`
			URL    string `json:"url"`
			At     string `json:"at"`
			File   string `json:"file"`
			Status int    `json:"status"`
		}
		if json.Unmarshal(scanner.Bytes(), &event) != nil || event.Kind != "response.body" || event.Status != 200 {
			continue
		}
		u, e := url.Parse(event.URL)
		if e != nil || u.Scheme != media.Scheme || u.Host != media.Host || u.Path != media.Path {
			continue
		}
		at, e := time.Parse(time.RFC3339Nano, event.At)
		if e != nil || at.Before(captured) {
			continue
		}
		if requireVOD {
			if at.After(captured.Add(20 * time.Minute)) {
				continue
			}
		} else {
			// Recorded candidate IDs keep their first-seen clock. Require a
			// recent real response for the exact resource after a normal replay.
			now := time.Now()
			if at.Before(now.Add(-20*time.Minute)) || at.After(now.Add(30*time.Second)) {
				continue
			}
		}
		path, e := filepath.EvalSymlinks(event.File)
		if e != nil {
			continue
		}
		rel, e := filepath.Rel(root, path)
		if e != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) || filepath.IsAbs(rel) {
			continue
		}
		info, e := os.Stat(path)
		if e != nil || info.Size() > 2*1024*1024 {
			continue
		}
		body, e := os.ReadFile(path)
		if e != nil {
			continue
		}
		lines := strings.Split(strings.TrimSpace(string(body)), "\n")
		if len(lines) == 0 || lines[0] != "#EXTM3U" || lines[len(lines)-1] != "#EXT-X-ENDLIST" {
			continue
		}
		vod, eventStream, valid, count, segments, duration := false, false, true, 0, 0, 0.0
		for _, line := range lines {
			if line == "#EXT-X-PLAYLIST-TYPE:VOD" {
				vod = true
			}
			if line == "#EXT-X-PLAYLIST-TYPE:EVENT" {
				eventStream = true
			}
			if strings.HasPrefix(line, "#EXTINF:") {
				v, e := strconv.ParseFloat(strings.Split(strings.TrimPrefix(line, "#EXTINF:"), ",")[0], 64)
				if e != nil || math.IsNaN(v) || math.IsInf(v, 0) || v <= 0 {
					valid = false
				}
				count++
				duration += v
			} else if line != "" && !strings.HasPrefix(line, "#") {
				segments++
			}
		}
		if (vod || !requireVOD) && !eventStream && valid && count > 0 && count == segments && duration >= 60 {
			return true
		}
	}
	return false
}
