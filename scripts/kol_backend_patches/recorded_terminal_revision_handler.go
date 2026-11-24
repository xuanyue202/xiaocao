package api

import (
	"bytes"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"time"

	fstream "github.com/GopeedLab/gopeed/pkg/protocol/stream"
	"github.com/gin-gonic/gin"
)

// The exact task remains paused. No URL or key is accepted in the request or
// emitted in the response; the validated provider ticket stays in RAM only.
func (c *APIClient) handlePrepareRecordedTerminalRevision(ctx *gin.Context) {
	host, _, err := net.SplitHostPort(ctx.Request.RemoteAddr)
	if err != nil || net.ParseIP(host) == nil || !net.ParseIP(host).IsLoopback() {
		ctx.JSON(http.StatusForbidden, gin.H{"code": 403, "msg": "local exact repair only"})
		return
	}
	var body struct {
		ID          string `json:"id"`
		Candidate   string `json:"candidate_id"`
		Resource    string `json:"resource_id"`
		FileID      string `json:"media_file_id"`
		PartialSHA  string `json:"partial_sha256"`
		ManifestSHA string `json:"manifest_sha256"`
		ResourceSHA string `json:"resource_sha256"`
		BindingSHA  string `json:"checkpoint_binding_sha256"`
		TerminalSHA string `json:"terminal_sha256"`
		AliasID     string `json:"alias_candidate_id"`
	}
	data, readErr := io.ReadAll(io.LimitReader(ctx.Request.Body, 8193))
	if readErr != nil || len(data) > 8192 {
		ctx.JSON(http.StatusBadRequest, gin.H{"code": 400, "msg": "invalid recorded repair binding"})
		return
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var trailing any
	if decoder.Decode(&body) != nil || decoder.Decode(&trailing) != io.EOF || body.ID == "" || body.Candidate == "" || body.AliasID == "" {
		ctx.JSON(http.StatusBadRequest, gin.H{"code": 400, "msg": "invalid recorded repair binding"})
		return
	}
	task, snapshotErr := c.downloader.RecordedRepairTaskSnapshot(body.ID)
	if snapshotErr != nil || task == nil || task.Meta == nil || task.Meta.Req == nil {
		ctx.JSON(http.StatusConflict, gin.H{"code": 409, "msg": "original recorded task unavailable"})
		return
	}
	labels := task.Meta.Req.Labels
	if labels["capture_id"] != body.Candidate || labels["recorded_resource_id"] != body.Resource ||
		labels["recorded_media_file_id"] != body.FileID {
		ctx.JSON(http.StatusConflict, gin.H{"code": 409, "msg": "original recorded task binding changed"})
		return
	}
	extra := make(map[string]string, len(labels)+1)
	for key, value := range labels {
		extra[key] = value
	}
	extra["recorded_ticket_candidate_id"] = body.AliasID
	request := DownloadTaskPayload{URL: task.Meta.Req.URL, Extra: extra}
	if err := resolveXiaocaoCaptureDownloadWithTerminalAlias(&request, c.cfg.RootDir, true); err != nil {
		ctx.JSON(http.StatusConflict, gin.H{"code": 409, "msg": "fresh recorded ticket evidence invalid"})
		return
	}
	candidates, err := loadEliveSourceJobCandidates(c.cfg.RootDir)
	if err != nil {
		ctx.JSON(http.StatusConflict, gin.H{"code": 409, "msg": "fresh recorded candidate unavailable"})
		return
	}
	var expiry time.Time
	for _, candidate := range candidates {
		if candidate.ID != body.AliasID {
			continue
		}
		if !expiry.IsZero() {
			ctx.JSON(http.StatusConflict, gin.H{"code": 409, "msg": "fresh recorded candidate ambiguous"})
			return
		}
		captured, parseErr := time.ParseInLocation("2006-01-02 15:04:05", candidate.Captured, time.Local)
		if parseErr != nil {
			ctx.JSON(http.StatusConflict, gin.H{"code": 409, "msg": "fresh recorded candidate time invalid"})
			return
		}
		expiry = captured.Add(20 * time.Minute)
	}
	if expiry.IsZero() || !expiry.After(time.Now()) {
		ctx.JSON(http.StatusConflict, gin.H{"code": 409, "msg": "fresh recorded candidate expired"})
		return
	}
	if limit := time.Now().Add(15 * time.Minute); expiry.After(limit) {
		expiry = limit
	}
	receipt, err := c.downloader.PrepareRecordedTerminalRevision(body.ID, body.Candidate, body.Resource,
		body.FileID, body.PartialSHA, body.ManifestSHA, body.ResourceSHA, body.BindingSHA, body.TerminalSHA, body.AliasID)
	if err != nil {
		ctx.JSON(http.StatusConflict, gin.H{"code": 409, "msg": "recorded task revision not prepared"})
		return
	}
	if !fstream.StoreRecoveryTicket(receipt.Revision, request.URL, expiry) {
		ctx.JSON(http.StatusConflict, gin.H{"code": 409, "msg": "recorded ticket memory binding unavailable; reconcile revision"})
		return
	}
	ctx.JSON(http.StatusOK, gin.H{"code": 0, "msg": "ok", "data": receipt})
}

// Starts only the exact prepared original task. It never invokes the generic
// resume endpoint, which may pause unrelated active provider tasks.
func (c *APIClient) handleStartRecordedTerminalRevision(ctx *gin.Context) {
	host, _, err := net.SplitHostPort(ctx.Request.RemoteAddr)
	if err != nil || net.ParseIP(host) == nil || !net.ParseIP(host).IsLoopback() {
		ctx.JSON(http.StatusForbidden, gin.H{"code": 403, "msg": "local exact repair only"})
		return
	}
	var body struct {
		ID       string `json:"id"`
		Revision string `json:"revision"`
	}
	data, err := io.ReadAll(io.LimitReader(ctx.Request.Body, 4097))
	if err != nil || len(data) > 4096 {
		ctx.JSON(http.StatusBadRequest, gin.H{"code": 400, "msg": "invalid recorded resume binding"})
		return
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var trailing any
	if decoder.Decode(&body) != nil || decoder.Decode(&trailing) != io.EOF || body.ID == "" || body.Revision == "" {
		ctx.JSON(http.StatusBadRequest, gin.H{"code": 400, "msg": "invalid recorded resume binding"})
		return
	}
	if err := c.downloader.StartRecordedTerminalRevision(body.ID, body.Revision); err != nil {
		ctx.JSON(http.StatusConflict, gin.H{"code": 409, "msg": "recorded exact task was not started"})
		return
	}
	ctx.JSON(http.StatusOK, gin.H{"code": 0, "msg": "ok", "data": gin.H{"id": body.ID, "revision": body.Revision}})
}
