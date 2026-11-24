package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestRecordedTerminalRevisionRejectsRemoteAndUnexpectedInput(t *testing.T) {
	gin.SetMode(gin.TestMode)
	client := &APIClient{}
	for _, test := range []struct {
		remote, body string
		status       int
	}{
		{"192.0.2.1:1234", `{}`, http.StatusForbidden},
		{"127.0.0.1:1234", `{"id":"task","candidate_id":"c","alias_candidate_id":"a","url":"private-ticket"}`, http.StatusBadRequest},
		{"127.0.0.1:1234", `{"id":"task","candidate_id":"c","alias_candidate_id":"a"} {}`, http.StatusBadRequest},
	} {
		recorder := httptest.NewRecorder()
		ctx, _ := gin.CreateTestContext(recorder)
		ctx.Request = httptest.NewRequest(http.MethodPost, "/", strings.NewReader(test.body))
		ctx.Request.RemoteAddr = test.remote
		client.handlePrepareRecordedTerminalRevision(ctx)
		if recorder.Code != test.status || strings.Contains(recorder.Body.String(), "private-ticket") {
			t.Fatalf("unsafe input was not rejected cleanly: status %d", recorder.Code)
		}
	}
}

func TestRecordedTerminalStartRejectsRemoteAndUnknownInput(t *testing.T) {
	gin.SetMode(gin.TestMode)
	client := &APIClient{}
	for _, test := range []struct {
		remote, body string
		status       int
	}{
		{"192.0.2.1:1234", `{}`, http.StatusForbidden},
		{"127.0.0.1:1234", `{"id":"task","revision":"revision","url":"private-ticket"}`, http.StatusBadRequest},
		{"127.0.0.1:1234", `{"id":"task","revision":"revision"} {}`, http.StatusBadRequest},
	} {
		recorder := httptest.NewRecorder()
		ctx, _ := gin.CreateTestContext(recorder)
		ctx.Request = httptest.NewRequest(http.MethodPost, "/", strings.NewReader(test.body))
		ctx.Request.RemoteAddr = test.remote
		client.handleStartRecordedTerminalRevision(ctx)
		if recorder.Code != test.status || strings.Contains(recorder.Body.String(), "private-ticket") {
			t.Fatalf("unsafe start input accepted: %d", recorder.Code)
		}
	}
}
