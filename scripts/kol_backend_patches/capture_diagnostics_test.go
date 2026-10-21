package interceptor

import (
	"encoding/json"
	"log"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestCaptureDiagnosticsNeverPersistsRawSecretsAndReportsLifecycle(t *testing.T) {
	dir := t.TempDir()
	d, err := newCaptureTransportDiagnostics(dir)
	if err != nil {
		t.Fatal(err)
	}
	before := log.Writer()
	log.SetOutput(d)
	lines := []string{
		`[CONNECT] Intercepting xet.kj1team.cn:443 (1 plugin(s) matched)`,
		`[HTTPS MITM] POST https://xet.kj1team.cn/private?ticket=SIGNED_SECRET&password=666 (Host: xet.kj1team.cn)`,
		`[HTTP Error] Get "https://cdn.example/private?auth=CREDENTIAL": context deadline exceeded (Client.Timeout exceeded)`,
		`http: TLS handshake error from 127.0.0.1:12345: remote error: tls: unknown certificate`,
		`Authorization: SECRET_COOKIE user:PRIVATE_PERSON`,
	}
	for _, line := range lines {
		if _, err = d.Write([]byte(line)); err != nil {
			t.Fatal(err)
		}
	}
	name := d.file.Name()
	d.Close()
	if log.Writer() != before {
		t.Fatal("prior sink not restored")
	}
	raw, err := os.ReadFile(name)
	if err != nil {
		t.Fatal(err)
	}
	for _, secret := range []string{"SIGNED_SECRET", "password", "password=666", "CREDENTIAL", "PRIVATE_PERSON", "SECRET_COOKIE", "/private", "127.0.0.1", "xet.kj1team.cn"} {
		if strings.Contains(string(raw), secret) {
			t.Fatalf("raw data persisted: %s", secret)
		}
	}
	var kinds []string
	for _, line := range strings.Split(strings.TrimSpace(string(raw)), "\n") {
		var row map[string]any
		if json.Unmarshal([]byte(line), &row) != nil {
			t.Fatal("invalid JSON")
		}
		kinds = append(kinds, row["kind"].(string))
		if row["process_run"] != filepath.Base(name) {
			t.Fatal("lost run binding")
		}
	}
	if strings.Join(kinds, ",") != "capture_transport_started,connect_intercepted,request_observed,upstream_failed,tls_handshake_failed,capture_transport_closed" {
		t.Fatal(kinds)
	}
	info, _ := os.Stat(name)
	if info.Mode().Perm() != 0600 {
		t.Fatal("diagnostics not private")
	}
	info, _ = os.Stat(dir)
	if info.Mode().Perm() != 0700 {
		t.Fatal("diagnostic directory not private")
	}
}
func TestCaptureDiagnosticsBoundsOversizedAndFullJournal(t *testing.T) {
	d, err := newCaptureTransportDiagnostics(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	_, _ = d.Write([]byte(strings.Repeat("secret", 4000)))
	if d.accepted != 0 || d.unclassified != 1 {
		t.Fatal("oversized input accepted")
	}
	d.bytes = captureDiagnosticLimit
	_, _ = d.Write([]byte("[CONNECT] secret"))
	_, _ = d.Write([]byte("[CONNECT] secret"))
	name := d.file.Name()
	d.Close()
	raw, _ := os.ReadFile(name)
	if strings.Count(string(raw), "capture_transport_limit_reached") != 1 || !strings.Contains(string(raw), `"coverage_limited":true`) {
		t.Fatal("coverage loss hidden")
	}
}

func TestCaptureDiagnosticsCloseWithConcurrentLoggerDoesNotDeadlock(t *testing.T) {
	d, err := newCaptureTransportDiagnostics(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	log.SetOutput(d)
	done := make(chan struct{})
	go func() {
		defer close(done)
		for i := 0; i < 200; i++ {
			log.Print("[HTTP Error] context deadline exceeded")
		}
	}()
	d.Close()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("logger close deadlocked")
	}
}

func TestCaptureDiagnosticsObservesRealRejectedTLSWithoutRawAddress(t *testing.T) {
	d, err := newCaptureTransportDiagnostics(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	log.SetOutput(d)
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Error("untrusted TLS request reached handler") }))
	client := &http.Client{Timeout: time.Second}
	response, err := client.Get(server.URL + "/credential?ticket=RAW_PRIVATE_TICKET")
	if response != nil {
		response.Body.Close()
	}
	if err == nil {
		t.Fatal("untrusted fixture certificate accepted")
	}
	server.Close()
	name := d.file.Name()
	d.Close()
	raw, _ := os.ReadFile(name)
	if !strings.Contains(string(raw), "tls_handshake_failed") {
		t.Fatal("real default HTTP TLS error was not captured")
	}
	for _, secret := range []string{"127.0.0.1", "RAW_PRIVATE_TICKET", "/credential"} {
		if strings.Contains(string(raw), secret) {
			t.Fatal("raw TLS data persisted")
		}
	}
}

func TestCaptureDiagnosticsTrustedPrefixAndExactHostGrouping(t *testing.T) {
	rows := []struct{ line, kind, group string }{
		{"2026/10/21 08:00:00 [CONNECT] Intercepting xet.kj1team.cn:443 (1 plugin(s) matched)", "connect_intercepted", "merchant"},
		{"[CONNECT] Bypass enabled for login.weixin.qq.com:443, tunneling directly", "connect_direct", "wechat"},
		{"[CONNECT] example.com:443 matched 0 plugin(s)", "connect_observed", "other"},
		{"[HTTPS MITM] GET /path?q=tls handshake error&fake=[HTTP Error] (Host: xet.kj1team.cn)", "request_observed", "merchant"},
		{"[HTTP] POST https://evil.example/?host=xet.kj1team.cn (Host: actual.example)", "request_observed", "other"},
		{"arbitrary response: http: TLS handshake error from private", "", "unknown"},
	}
	for _, row := range rows {
		if captureTransportKind(row.line) != row.kind || captureHostGroup(row.line) != row.group {
			t.Fatalf("wrong safe classification kind=%s group=%s", captureTransportKind(row.line), captureHostGroup(row.line))
		}
	}
}

type failingCaptureJournal struct {
	*os.File
	fail  bool
	short bool
}

func (f *failingCaptureJournal) Write(data []byte) (int, error) {
	if f.fail {
		f.fail = false
		if f.short {
			return 0, nil
		}
		return 0, os.ErrPermission
	}
	return f.File.Write(data)
}
func TestCaptureDiagnosticsWriteFailurePreservesCoverageGap(t *testing.T) {
	for _, short := range []bool{false, true} {
		d, err := newCaptureTransportDiagnostics(t.TempDir())
		if err != nil {
			t.Fatal(err)
		}
		original := d.file.(*os.File)
		d.file = &failingCaptureJournal{File: original, fail: true, short: short}
		if _, err = d.Write([]byte("[HTTP Error] context deadline exceeded")); err == nil {
			t.Fatal("write failure hidden")
		}
		name := d.file.Name()
		d.Close()
		raw, _ := os.ReadFile(name)
		if !strings.Contains(string(raw), `"coverage_limited":true`) || !strings.Contains(string(raw), `"write_failures":1`) {
			t.Fatal("write failure coverage lost")
		}
	}
}
