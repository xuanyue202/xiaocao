package api

import (
	"github.com/gin-gonic/gin"
	"net"
	"net/http"
)

func (c *APIClient) handlePrepareIncompleteStreamRevision(ctx *gin.Context) {
	host, _, err := net.SplitHostPort(ctx.Request.RemoteAddr)
	if err != nil || net.ParseIP(host) == nil || !net.ParseIP(host).IsLoopback() {
		ctx.JSON(http.StatusForbidden, gin.H{"code": 403, "msg": "local exact repair only"})
		return
	}
	var body struct {
		ID        string `json:"id"`
		Candidate string `json:"candidate_id"`
		Live      string `json:"live_id"`
		SHA       string `json:"original_sha256"`
	}
	if ctx.ShouldBindJSON(&body) != nil || body.ID == "" || body.Candidate == "" || body.Live == "" || len(body.SHA) != 64 {
		ctx.JSON(http.StatusBadRequest, gin.H{"code": 400, "msg": "invalid exact stream revision binding"})
		return
	}
	receipt, err := c.downloader.PrepareIncompleteStreamRevision(body.ID, body.Candidate, body.Live, body.SHA)
	if err != nil {
		ctx.JSON(http.StatusConflict, gin.H{"code": 409, "msg": err.Error()})
		return
	}
	ctx.JSON(http.StatusOK, gin.H{"code": 0, "msg": "ok", "data": receipt})
}
