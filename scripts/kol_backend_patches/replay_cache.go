package stream

// Finite HLS transport checkpoints belong to the existing downloader task.
// Only verified complete segments are reused. Credentials stay in memory;
// manifests on disk contain hashes/counts, never URLs, headers or key text.
import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

const replayRequestTimeout = 25 * time.Second
const replayResourceAttempts = 3

func replayFFmpegNetworkOptions() []string {
	// The local HTTP reader must outlive every bounded whole-segment retry.
	budget := replayRequestTimeout*time.Duration(replayResourceAttempts) + 15*time.Second
	return []string{"-safe", "0", "-protocol_whitelist", "file,http,tcp,crypto,data", "-rw_timeout", fmt.Sprint(budget.Microseconds()), "-reconnect", "1", "-reconnect_on_network_error", "1", "-reconnect_streamed", "1", "-reconnect_max_retries", "3", "-reconnect_delay_max", "5", "-reconnect_delay_total_max", "60"}
}

type replayResource struct {
	upstream string
	segment  bool
	mu       sync.Mutex
}
type replayCache struct {
	root, token     string
	resources       map[string]*replayResource
	playlist        []byte
	periods         [][]byte
	periodDurations []float64
	headers         map[string]string
	client          *http.Client
	server          *http.Server
	listener        net.Listener
	context         context.Context
	cancel          context.CancelFunc
	mu              sync.Mutex
	verified        map[string]bool
	duration        float64
	total           int
}
type replayBlobProof struct {
	SHA256 string `json:"sha256"`
	Size   int64  `json:"size"`
}

var replayURI = regexp.MustCompile(`URI="([^"]+)"`)

func replayDigest(data []byte) string { sum := sha256.Sum256(data); return hex.EncodeToString(sum[:]) }
func replayFileProof(name string) (replayBlobProof, error) {
	file, err := os.Open(name)
	if err != nil {
		return replayBlobProof{}, err
	}
	defer file.Close()
	hash := sha256.New()
	size, err := io.Copy(hash, file)
	if err != nil {
		return replayBlobProof{}, err
	}
	return replayBlobProof{hex.EncodeToString(hash.Sum(nil)), size}, nil
}
func writeReplayJSON(name string, value any) error {
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	tmp := name + ".tmp"
	if err = os.WriteFile(tmp, data, 0600); err != nil {
		return err
	}
	return os.Rename(tmp, name)
}
func newReplayCache(rawURL string, headers map[string]string, root, binding string) (*replayCache, error) {
	if _, err := os.Stat(filepath.Join(root, "terminal.json")); err == nil {
		return nil, fmt.Errorf("replay checkpoint authentication terminal")
	} else if !os.IsNotExist(err) {
		return nil, fmt.Errorf("replay terminal state unreadable")
	}
	base, err := url.Parse(rawURL)
	if err != nil || (base.Scheme != "http" && base.Scheme != "https") || base.User != nil {
		return nil, fmt.Errorf("invalid replay origin")
	}
	ctx, cancel := context.WithCancel(context.Background())
	c := &replayCache{root: root, headers: headers, resources: map[string]*replayResource{}, verified: map[string]bool{}, client: &http.Client{Timeout: replayRequestTimeout}, context: ctx, cancel: cancel}
	initialIP := net.ParseIP(base.Hostname())
	allowLocal := initialIP != nil && initialIP.IsLoopback()
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil // FFmpeg's original source path is direct; no capture PAC takeover.
	transport.DialContext = func(callContext context.Context, network, address string) (net.Conn, error) {
		host, port, splitErr := net.SplitHostPort(address)
		if splitErr != nil {
			return nil, fmt.Errorf("invalid media address")
		}
		ips, lookupErr := net.DefaultResolver.LookupIPAddr(callContext, host)
		if lookupErr != nil {
			return nil, fmt.Errorf("media DNS unavailable")
		}
		for _, entry := range ips {
			ip := entry.IP
			if !allowLocal && (ip.IsPrivate() || ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsUnspecified() || ip.IsMulticast()) {
				return nil, fmt.Errorf("nonpublic media address rejected")
			}
		}
		dialer := net.Dialer{Timeout: 20 * time.Second}
		for _, entry := range ips {
			connection, dialErr := dialer.DialContext(callContext, network, net.JoinHostPort(entry.IP.String(), port))
			if dialErr == nil {
				return connection, nil
			}
		}
		return nil, fmt.Errorf("media connection unavailable")
	}
	c.client.Transport = transport
	c.client.CheckRedirect = func(next *http.Request, prior []*http.Request) error {
		if len(prior) >= 5 || next.URL.Scheme+"://"+next.URL.Host != prior[0].URL.Scheme+"://"+prior[0].URL.Host {
			return fmt.Errorf("cross-origin media redirect rejected")
		}
		return nil
	}
	req, err := http.NewRequestWithContext(ctx, "GET", rawURL, nil)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("invalid replay request")
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	response, err := c.client.Do(req)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("replay manifest transport failed")
	}
	defer response.Body.Close()
	if response.StatusCode == 401 || response.StatusCode == 403 {
		if err := os.MkdirAll(root, 0700); err != nil {
			cancel()
			return nil, fmt.Errorf("terminal checkpoint directory unavailable")
		}
		if err := writeReplayJSON(filepath.Join(root, "terminal.json"), map[string]int{"status": response.StatusCode}); err != nil {
			cancel()
			return nil, fmt.Errorf("terminal checkpoint persistence failed")
		}
	}
	if response.StatusCode != 200 {
		cancel()
		return nil, fmt.Errorf("replay manifest status %d", response.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, 4*1024*1024+1))
	if err != nil || len(body) > 4*1024*1024 {
		cancel()
		return nil, fmt.Errorf("replay manifest incomplete")
	}
	base = response.Request.URL
	text := string(body)
	if !strings.Contains(text, "#EXT-X-ENDLIST") || strings.Contains(text, "#EXT-X-STREAM-INF") || strings.Contains(text, "#EXT-X-BYTERANGE") {
		cancel()
		return nil, fmt.Errorf("unsupported finite replay manifest")
	}
	headerIdentity, _ := json.Marshal(headers)
	binding = binding + ":" + replayDigest(headerIdentity) + ":" + replayDigest([]byte(base.String()))
	c.token = replayDigest([]byte(binding + "\n" + rawURL))[:32]
	rewrite := func(reference string, segment bool) (string, error) {
		parsed, e := url.Parse(reference)
		if e != nil {
			return "", fmt.Errorf("invalid replay resource")
		}
		absolute := base.ResolveReference(parsed)
		if (absolute.Scheme != "http" && absolute.Scheme != "https") || absolute.User != nil || !allowedReplayResource(base, absolute, headers) {
			return "", fmt.Errorf("invalid replay resource scheme")
		}
		extension := filepath.Ext(absolute.Path)
		if !regexp.MustCompile(`^\.[a-zA-Z0-9]{1,8}$`).MatchString(extension) {
			extension = ".bin"
		}
		key := replayDigest([]byte(absolute.String())) + extension
		if prior, ok := c.resources[key]; ok {
			prior.segment = prior.segment || segment
		} else {
			c.resources[key] = &replayResource{upstream: absolute.String(), segment: segment}
		}
		return "/" + c.token + "/" + key, nil
	}
	var output []string
	for _, line := range strings.Split(text, "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed != "" && !strings.HasPrefix(trimmed, "#") {
			line, err = rewrite(trimmed, true)
		} else if strings.Contains(trimmed, "URI=\"") {
			var replaceErr error
			line = replayURI.ReplaceAllStringFunc(line, func(value string) string {
				match := replayURI.FindStringSubmatch(value)
				local, e := rewrite(match[1], false)
				if e != nil {
					replaceErr = e
				}
				return "URI=\"" + local + "\""
			})
			err = replaceErr
		}
		if err != nil {
			cancel()
			return nil, err
		}
		output = append(output, line)
	}
	for _, resource := range c.resources {
		if resource.segment {
			c.total++
		}
	}
	var duration float64
	for _, line := range strings.Split(text, "\n") {
		if strings.HasPrefix(line, "#EXTINF:") {
			raw := strings.SplitN(strings.TrimPrefix(line, "#EXTINF:"), ",", 2)[0]
			value, parseErr := strconv.ParseFloat(raw, 64)
			if parseErr != nil || math.IsNaN(value) || math.IsInf(value, 0) || value <= 0 {
				cancel()
				return nil, fmt.Errorf("invalid segment duration")
			}
			duration += value
		}
	}
	c.duration = duration
	if c.total == 0 || duration <= 0 {
		cancel()
		return nil, fmt.Errorf("replay contains no segments")
	}
	if info, statErr := os.Lstat(root); statErr == nil && (!info.IsDir() || info.Mode()&os.ModeSymlink != 0) {
		cancel()
		return nil, fmt.Errorf("invalid checkpoint directory")
	}
	if err = os.MkdirAll(root, 0700); err != nil {
		cancel()
		return nil, fmt.Errorf("replay checkpoint directory failed")
	}
	proof := struct {
		Binding, Manifest string
		Segments          int
	}{replayDigest([]byte(binding + "\n" + rawURL)), replayDigest(body), c.total}
	proofBytes, _ := json.Marshal(proof)
	saved, readErr := os.ReadFile(filepath.Join(root, "binding.json"))
	if readErr == nil && string(saved) != string(proofBytes) {
		cancel()
		return nil, fmt.Errorf("replay checkpoint binding changed")
	}
	if readErr != nil && !os.IsNotExist(readErr) {
		cancel()
		return nil, fmt.Errorf("replay checkpoint binding unreadable")
	}
	if readErr != nil {
		if err = writeReplayJSON(filepath.Join(root, "binding.json"), proof); err != nil {
			cancel()
			return nil, err
		}
	}
	c.playlist = []byte(strings.Join(output, "\n"))
	c.periods, c.periodDurations, err = replayPeriods(output)
	if err != nil {
		cancel()
		return nil, err
	}
	c.listener, err = net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		cancel()
		return nil, err
	}
	c.server = &http.Server{Handler: http.HandlerFunc(c.serve), ReadHeaderTimeout: 5 * time.Second}
	go c.server.Serve(c.listener)
	return c, nil
}
func (c *replayCache) URL() string {
	return "http://" + c.listener.Addr().String() + "/" + c.token + "/input.ffconcat"
}

// Each declared discontinuity gets its own HLS demuxer. Concatenating TS bytes
// across that boundary can mark an otherwise complete PES corrupt in FFmpeg.
// Keep every source segment and strict decode/duration checks; do not discard
// corrupt packets or infer new discontinuities from a decode error.
func replayPeriods(lines []string) ([][]byte, []float64, error) {
	var headers, body []string
	var periods [][]byte
	var durations []float64
	var sequence uint64
	var count uint64
	var duration float64
	var activeKey, activeMap, mapKey string
	var pending float64
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "#EXT-X-MEDIA-SEQUENCE:") {
			var err error
			sequence, err = strconv.ParseUint(strings.TrimPrefix(line, "#EXT-X-MEDIA-SEQUENCE:"), 10, 64)
			if err != nil {
				return nil, nil, fmt.Errorf("invalid replay media sequence")
			}
		} else if line == "#EXTM3U" || strings.HasPrefix(line, "#EXT-X-VERSION:") || strings.HasPrefix(line, "#EXT-X-TARGETDURATION:") || strings.HasPrefix(line, "#EXT-X-PLAYLIST-TYPE:") || line == "#EXT-X-INDEPENDENT-SEGMENTS" {
			headers = append(headers, line)
		}
	}
	start := func() {
		body = append([]string{}, headers...)
		body = append(body, "#EXT-X-MEDIA-SEQUENCE:"+strconv.FormatUint(sequence+count, 10))
		if activeMap != "" {
			if mapKey != "" {
				body = append(body, mapKey)
			}
			body = append(body, activeMap)
		}
		if activeKey != "" && (activeMap == "" || activeKey != mapKey) {
			body = append(body, activeKey)
		}
	}
	finish := func() {
		if duration > 0 {
			periods = append(periods, []byte(strings.Join(append(body, "#EXT-X-ENDLIST"), "\n")+"\n"))
			durations = append(durations, duration)
		}
		duration = 0
	}
	start()
	for _, raw := range lines {
		line := strings.TrimSpace(raw)
		if line == "#EXT-X-DISCONTINUITY" {
			if pending != 0 {
				return nil, nil, fmt.Errorf("discontinuity splits replay segment")
			}
			finish()
			start()
			continue
		}
		if line == "#EXTM3U" || line == "#EXT-X-ENDLIST" || strings.HasPrefix(line, "#EXT-X-VERSION:") || strings.HasPrefix(line, "#EXT-X-TARGETDURATION:") || strings.HasPrefix(line, "#EXT-X-PLAYLIST-TYPE:") || strings.HasPrefix(line, "#EXT-X-MEDIA-SEQUENCE:") || strings.HasPrefix(line, "#EXT-X-DISCONTINUITY-SEQUENCE:") || line == "#EXT-X-INDEPENDENT-SEGMENTS" {
			continue
		}
		if strings.HasPrefix(line, "#EXT-X-KEY:") {
			activeKey = line
		}
		if strings.HasPrefix(line, "#EXT-X-MAP:") {
			activeMap = line
			mapKey = activeKey
		}
		if strings.HasPrefix(line, "#EXTINF:") {
			var err error
			pending, err = strconv.ParseFloat(strings.SplitN(strings.TrimPrefix(line, "#EXTINF:"), ",", 2)[0], 64)
			if err != nil || pending <= 0 || math.IsNaN(pending) || math.IsInf(pending, 0) {
				return nil, nil, fmt.Errorf("invalid replay period duration")
			}
		} else if line != "" && !strings.HasPrefix(line, "#") {
			if pending <= 0 {
				return nil, nil, fmt.Errorf("replay segment lacks duration")
			}
			duration += pending
			pending = 0
			count++
		}
		body = append(body, line)
	}
	if pending != 0 {
		return nil, nil, fmt.Errorf("replay period has incomplete segment")
	}
	finish()
	return periods, durations, nil
}
func (c *replayCache) Close() {
	c.cancel()
	c.client.CloseIdleConnections()
	if c.server != nil {
		_ = c.server.Close()
	}
}
func (c *replayCache) Complete() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	for key, resource := range c.resources {
		if resource.segment && !c.verified[key] {
			return false
		}
	}
	return true
}
func (c *replayCache) mark(key string) { c.mu.Lock(); c.verified[key] = true; c.mu.Unlock() }
func (c *replayCache) blob(key string, resource *replayResource) (string, error) {
	resource.mu.Lock()
	defer resource.mu.Unlock()
	target := filepath.Join(c.root, key+".bin")
	proofFile := target + ".json"
	var terminal struct {
		Status int `json:"status"`
	}
	if data, readErr := os.ReadFile(filepath.Join(c.root, "terminal.json")); readErr == nil {
		if json.Unmarshal(data, &terminal) != nil || (terminal.Status != 401 && terminal.Status != 403) {
			return "", fmt.Errorf("invalid terminal checkpoint")
		}
		return "", replayHTTPError{terminal.Status}
	}

	if _, err := os.Stat(filepath.Join(c.root, "terminal.json")); !os.IsNotExist(err) {
		return "", fmt.Errorf("terminal checkpoint unreadable")
	}
	var saved replayBlobProof
	if data, err := os.ReadFile(proofFile); err == nil {
		if json.Unmarshal(data, &saved) != nil {
			return "", fmt.Errorf("replay checkpoint proof invalid")
		}
		actual, e := replayFileProof(target)
		if e == nil && saved == actual && actual.Size > 0 {
			c.mark(key)
			return target, nil
		}
		return "", fmt.Errorf("replay checkpoint hash mismatch")
	}
	if _, err := os.Stat(proofFile); !os.IsNotExist(err) {
		return "", fmt.Errorf("replay checkpoint proof unreadable")
	}
	partial := target + ".partial"
	var last error
	for attempt := 0; attempt < replayResourceAttempts; attempt++ {
		if err := c.context.Err(); err != nil {
			return "", err
		}
		req, err := http.NewRequestWithContext(c.context, "GET", resource.upstream, nil)
		if err != nil {
			return "", fmt.Errorf("invalid segment request")
		}
		for k, v := range c.headers {
			req.Header.Set(k, v)
		}
		req.Header.Set("Accept-Encoding", "identity")
		response, err := c.client.Do(req)
		if err != nil {
			last = fmt.Errorf("segment transport failed")
			continue
		}
		if response.StatusCode == 401 || response.StatusCode == 403 {
			response.Body.Close()
			terminal.Status = response.StatusCode
			if persistErr := writeReplayJSON(filepath.Join(c.root, "terminal.json"), terminal); persistErr != nil {
				return "", fmt.Errorf("terminal checkpoint persistence failed")
			}
			return "", replayHTTPError{response.StatusCode}
		}
		expected := response.ContentLength
		if response.StatusCode != 200 {
			response.Body.Close()
			last = fmt.Errorf("segment status %d", response.StatusCode)
			continue
		}
		// Checkpoints commit whole verified segments. A partial segment is
		// retried as one unit; never splice bytes without an origin validator.
		flags := os.O_CREATE | os.O_WRONLY | os.O_TRUNC
		file, e := os.OpenFile(partial, flags, 0600)
		if e != nil {
			response.Body.Close()
			return "", e
		}
		n, copyErr := io.Copy(file, io.LimitReader(response.Body, 128*1024*1024+1))
		response.Body.Close()
		syncErr := file.Sync()
		closeErr := file.Close()
		if copyErr != nil || (expected >= 0 && n != expected) || n > 128*1024*1024 || syncErr != nil || closeErr != nil {
			last = fmt.Errorf("segment body incomplete")
			continue
		}
		actual, e := replayFileProof(partial)
		if e != nil || actual.Size == 0 {
			return "", fmt.Errorf("empty segment")
		}
		if err = os.Rename(partial, target); err != nil {
			return "", err
		}
		if err = writeReplayJSON(proofFile, actual); err != nil {
			return "", err
		}
		c.mark(key)
		return target, nil
	}
	return "", last
}
func (c *replayCache) serve(w http.ResponseWriter, r *http.Request) {
	prefix := "/" + c.token + "/"
	if r.Method != "GET" && r.Method != "HEAD" {
		http.Error(w, "method unavailable", 405)
		return
	}
	if !strings.HasPrefix(r.URL.Path, prefix) {
		http.NotFound(w, r)
		return
	}
	key := strings.TrimPrefix(r.URL.Path, prefix)
	if key == "input.ffconcat" {
		var text strings.Builder
		text.WriteString("ffconcat version 1.0\n")
		for index, duration := range c.periodDurations {
			fmt.Fprintf(&text, "file 'http://%s/%s/period-%d.m3u8'\nduration %.9f\noption rw_timeout %d\n", c.listener.Addr().String(), c.token, index, duration, (replayRequestTimeout*time.Duration(replayResourceAttempts) + 15*time.Second).Microseconds())
		}
		w.Header().Set("Content-Type", "text/plain")
		w.Header().Set("Content-Length", strconv.Itoa(text.Len()))
		if r.Method != "HEAD" {
			_, _ = io.WriteString(w, text.String())
		}
		return
	}
	if strings.HasPrefix(key, "period-") && strings.HasSuffix(key, ".m3u8") {
		index, err := strconv.Atoi(strings.TrimSuffix(strings.TrimPrefix(key, "period-"), ".m3u8"))
		if err != nil || index < 0 || index >= len(c.periods) {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/vnd.apple.mpegurl")
		w.Header().Set("Content-Length", strconv.Itoa(len(c.periods[index])))
		if r.Method != "HEAD" {
			_, _ = w.Write(c.periods[index])
		}
		return
	}
	if key == "playlist.m3u8" {
		w.Header().Set("Content-Type", "application/vnd.apple.mpegurl")
		w.Header().Set("Content-Length", strconv.Itoa(len(c.playlist)))
		if r.Method != "HEAD" {
			_, _ = w.Write(c.playlist)
		}
		return
	}
	resource, ok := c.resources[key]
	if !ok {
		http.NotFound(w, r)
		return
	}
	name, err := c.blob(key, resource)
	if err != nil {
		var status replayHTTPError
		if errors.As(err, &status) {
			http.Error(w, "replay authentication rejected", status.status)
			return
		}
		http.Error(w, "replay segment unavailable", 502)
		return
	}
	file, err := os.Open(name)
	if err != nil {
		http.Error(w, "checkpoint unavailable", 500)
		return
	}
	defer file.Close()
	stamp, err := file.Stat()
	if err != nil {
		http.Error(w, "checkpoint unavailable", 500)
		return
	}
	http.ServeContent(w, r, "segment", stamp.ModTime(), file)
}

// The decoder's progress alone may end successfully after skipped HLS segments.
// Verify the finished container before deleting resumable source checkpoints.
func (c *replayCache) ValidateArtifact(name string, expected float64) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	output, err := exec.CommandContext(ctx, "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", name).Output()
	if err != nil {
		return fmt.Errorf("checkpoint artifact probe failed")
	}
	var result struct {
		Format struct {
			Duration string `json:"duration"`
		} `json:"format"`
	}
	if json.Unmarshal(output, &result) != nil {
		return fmt.Errorf("checkpoint artifact evidence invalid")
	}
	duration, err := strconv.ParseFloat(result.Format.Duration, 64)
	if err != nil {
		return fmt.Errorf("checkpoint artifact duration invalid")
	}
	return finiteStreamCompletionError(nil, expected, duration)
}

type replayHTTPError struct{ status int }

func (e replayHTTPError) Error() string { return "replay authentication rejected" }

// A reserved output may contain our interrupted transcode only after a bound
// checkpoint exists. A foreign artifact cannot be overwritten on first start.
func validateReplayReservation(name string, labels map[string]string) error {
	revision := labels["media_repair_revision"]
	if revision == "" {
		return nil
	}
	data, err := os.ReadFile(name + ".reservation.json")
	if err != nil {
		return fmt.Errorf("revision reservation missing")
	}
	var marker map[string]string
	if json.Unmarshal(data, &marker) != nil || marker["revision"] != revision || marker["previous_sha256"] != labels["media_repair_previous_sha256"] || marker["task_id"] != labels["media_repair_task_id"] || marker["candidate_id"] != labels["capture_id"] || marker["live_id"] != labels["live_id"] {
		return fmt.Errorf("revision reservation changed")
	}
	stamp, err := os.Lstat(name)
	if err != nil || !stamp.Mode().IsRegular() {
		return fmt.Errorf("revision output reservation invalid")
	}
	if stamp.Size() > 0 {
		if _, err = os.Stat(name + ".hls-cache/binding.json"); err != nil {
			return fmt.Errorf("revision output occupied before checkpoint start")
		}
	}
	return nil
}

// Only the observed unsigned Xiaoetong manifest may name exact provider-issued CDN URLs.
func allowedReplayResource(origin, resource *url.URL, headers map[string]string) bool {
	if origin.Scheme+"://"+origin.Host == resource.Scheme+"://"+resource.Host {
		return true
	}
	return len(headers) == 0 && origin.RawQuery == "" && origin.Fragment == "" && resource.Fragment == "" && origin.Scheme == "https" && origin.Host == "live-ex-speed.xiaoeknow.com" && resource.Scheme == "https" && resource.Host == "encrypt-k-vod.xet.tech" && resource.User == nil
}
