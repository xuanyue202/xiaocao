package stream

import (
	fstream "github.com/GopeedLab/gopeed/pkg/protocol/stream"
	"net/url"
	"os"
	"path/filepath"
	"testing"
)

func TestRecordedRecoveryOnlyUsesExactProviderPath(t *testing.T) {
	old := "https://encrypt-k-vod.xet.tech/account/a/drm/v.f123.m3u8?old=private"
	good := "https://encrypt-k-vod.xet.tech/account/a/drm/v.f123.m3u8?new=private"
	if !sameRecordedRecoveryPath(old, good) {
		t.Fatal("same exact resource rejected")
	}
	if !sameRecordedRecoveryPath(old, "https://t-vod.h5.xed.plus/account/a/drm/v.f123.m3u8?new=private") {
		t.Fatal("same exact path on the separately approved host rejected")
	}
	for _, bad := range []string{
		"https://encrypt-k-vod.xet.tech/account/b/drm/v.f123.m3u8?new=private",
		"https://encrypt-k-vod.xet.tech/account/%61/drm/v.f123.m3u8?new=private",
		"https://other.h5.xed.plus/account/a/drm/v.f123.m3u8?new=private",
		"https://encrypt-k-vod.xet.tech:443/account/a/drm/v.f123.m3u8?new=private",
		"http://encrypt-k-vod.xet.tech/account/a/drm/v.f123.m3u8?new=private",
		"https://user@encrypt-k-vod.xet.tech/account/a/drm/v.f123.m3u8?new=private",
		"https://encrypt-k-vod.xet.tech/account/a/drm/v.f123.m3u8#fragment",
	} {
		if sameRecordedRecoveryPath(old, bad) {
			t.Fatal("changed provider path accepted")
		}
	}
}

func TestRecordedRecoveryStartMarkerRejectsSecondStart(t *testing.T) {
	name := filepath.Join(t.TempDir(), "reserved.mp4")
	if err := markRecordedRecoveryStarted(name, "revision-a"); err != nil {
		t.Fatal(err)
	}
	before, err := os.ReadFile(name + ".recorded-started")
	if err != nil {
		t.Fatal(err)
	}
	if err := markRecordedRecoveryStarted(name, "revision-b"); err == nil {
		t.Fatal("second resume accepted")
	}
	after, err := os.ReadFile(name + ".recorded-started")
	if err != nil || string(after) != string(before) {
		t.Fatal("first marker changed")
	}
}

func TestRecordedRecoveryForbidsExtraHeaders(t *testing.T) {
	if !recordedRecoveryHeadersAllowed(&fstream.ReqExtra{}) {
		t.Fatal("empty headers rejected")
	}
	if recordedRecoveryHeadersAllowed(&fstream.ReqExtra{Header: map[string]string{"Authorization": "private"}}) || recordedRecoveryHeadersAllowed(nil) {
		t.Fatal("extra or untyped headers accepted")
	}
}

func TestRecordedTerminalAliasDoesNotAuthorizeCrossHostRedirect(t *testing.T) {
	old, _ := url.Parse("https://t-vod.h5.xed.plus/account/a/drm/v.f123.m3u8")
	cross, _ := url.Parse("https://encrypt-k-vod.xet.tech/account/a/drm/v.f123.m3u8")
	if allowedReplayRedirect(old, cross, true) {
		t.Fatal("cross-host redirect accepted")
	}
}
