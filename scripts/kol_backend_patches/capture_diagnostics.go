package interceptor

// Capture-only standard-log sink. Never persist raw messages/URLs/headers.
// These are transport observations, not WeChat security-decision reason codes.
import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

const captureDiagnosticLimit = 8 * 1024 * 1024

type captureDiagnosticJournal interface {
	io.Writer
	Name() string
	Sync() error
	Close() error
}

type captureTransportDiagnostics struct {
	mu                            sync.Mutex
	file                          captureDiagnosticJournal
	previous                      io.Writer
	run                           string
	bytes, accepted, unclassified int
	writeFailures                 int
	limited, closed               bool
}

var captureLogPrefix = regexp.MustCompile(`^[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)? `)
var captureRequestPrefix = regexp.MustCompile(`^\[(?:HTTPS MITM|HTTP)\] (?:GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH|CONNECT) `)
var captureHostSuffix = regexp.MustCompile(`\(Host: ([a-zA-Z0-9.-]+)(?::[0-9]+)?\)\s*$`)
var captureConnectHost = regexp.MustCompile(`^\[CONNECT\] (?:(?:Intercepting |Bypass enabled for ))?([a-zA-Z0-9.-]+):[0-9]+`)
var captureDynamicHost = regexp.MustCompile(`^\[Dynamic Server\] Started for ([a-zA-Z0-9.-]+) on port `)

func captureLogMessage(line string) string { return captureLogPrefix.ReplaceAllString(line, "") }
func captureHostGroup(line string) string {
	line = captureLogMessage(line)
	var match []string
	for _, pattern := range []*regexp.Regexp{captureHostSuffix, captureConnectHost, captureDynamicHost} {
		match = pattern.FindStringSubmatch(line)
		if len(match) >= 2 {
			break
		}
	}
	if len(match) < 2 {
		return "unknown"
	}
	host := strings.ToLower(match[1])
	for _, rule := range []struct{ suffix, group string }{{"kj1team.cn", "merchant"}, {"xiaoeknow.com", "xiaoetong"}, {"xet.tech", "xiaoetong"}, {"myqcloud.com", "media"}, {"qcloud.com", "media"}, {"weixin.qq.com", "wechat"}} {
		if host == rule.suffix || strings.HasSuffix(host, "."+rule.suffix) {
			return rule.group
		}
	}
	return "other"
}
func captureTransportKind(line string) string {
	line = captureLogMessage(line)
	switch {
	case strings.HasPrefix(line, "http: TLS handshake error"):
		return "tls_handshake_failed"
	case strings.HasPrefix(line, "[HTTP Error] ") || strings.HasPrefix(line, "[Tunnel Error] ") || strings.HasPrefix(line, "[MITM Error] "):
		// Remote error text can contain arbitrary URL/body words. Its trusted
		// prefix proves only the observed transport failure class.
		return "upstream_failed"
	case strings.HasPrefix(line, "[CONNECT] Intercepting "):
		return "connect_intercepted"
	case strings.HasPrefix(line, "[CONNECT] Bypass enabled for "):
		return "connect_direct"
	case strings.HasPrefix(line, "[CONNECT] "):
		return "connect_observed"
	case captureRequestPrefix.MatchString(line):
		return "request_observed"
	case strings.HasPrefix(line, "[Dynamic Server] Started for "):
		return "mitm_listener_started"
	default:
		return ""
	}
}

func newCaptureTransportDiagnostics(dir string) (*captureTransportDiagnostics, error) {
	if err := os.MkdirAll(dir, 0700); err != nil {
		return nil, fmt.Errorf("capture diagnostics directory unavailable")
	}
	if err := os.Chmod(dir, 0700); err != nil {
		return nil, fmt.Errorf("capture diagnostics permissions unavailable")
	}
	file, err := os.CreateTemp(dir, "transport-*.jsonl")
	if err != nil {
		return nil, fmt.Errorf("capture diagnostics file unavailable")
	}
	d := &captureTransportDiagnostics{file: file, previous: log.Writer(), run: filepath.Base(file.Name())}
	if err = d.record("capture_transport_started", "unknown"); err != nil {
		file.Close()
		return nil, err
	}
	return d, nil
}
func (d *captureTransportDiagnostics) record(kind, group string) error {
	row := map[string]any{"schema_version": 1, "observed_at": time.Now().UTC().Format(time.RFC3339Nano), "process_pid": os.Getpid(), "process_run": d.run, "kind": kind, "target_group": group}
	if kind == "capture_transport_closed" {
		row["accepted_events"] = d.accepted
		row["unclassified_messages"] = d.unclassified
		row["coverage_limited"] = d.limited
		row["write_failures"] = d.writeFailures
	}
	data, err := json.Marshal(row)
	if err != nil {
		return err
	}
	data = append(data, '\n')
	n, err := d.file.Write(data)
	d.bytes += n
	if err == nil && n != len(data) {
		err = io.ErrShortWrite
	}
	return err
}
func (d *captureTransportDiagnostics) Write(data []byte) (int, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.closed {
		return len(data), nil
	}
	if d.bytes >= captureDiagnosticLimit {
		if !d.limited {
			d.limited = true
			_ = d.record("capture_transport_limit_reached", "unknown")
		}
		return len(data), nil
	}
	// log.Logger supplies one complete record per Write. Bound classification
	// work and never split a hostile multiline value into new trusted events.
	if len(data) > 16384 {
		d.unclassified++
		return len(data), nil
	}
	kind := captureTransportKind(string(data))
	if kind == "" {
		d.unclassified++
		return len(data), nil
	}
	if err := d.record(kind, captureHostGroup(string(data))); err != nil {
		d.writeFailures++
		d.limited = true
		return 0, err
	}
	d.accepted++
	return len(data), nil
}
func (d *captureTransportDiagnostics) Close() {
	// Never hold our mutex while acquiring the standard logger's mutex:
	// an in-flight log call holds that mutex while entering Write.
	if log.Writer() == d {
		log.SetOutput(d.previous)
	}
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.closed {
		return
	}
	_ = d.record("capture_transport_closed", "unknown")
	_ = d.file.Sync()
	_ = d.file.Close()
	d.closed = true
}
func (c *Interceptor) stopCaptureDiagnostics() {
	if c.captureDiagnostics != nil {
		c.captureDiagnostics.Close()
		c.captureDiagnostics = nil
	}
}
