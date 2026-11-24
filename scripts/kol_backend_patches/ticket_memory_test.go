package stream

import (
	"testing"
	"time"
)

func TestRecoveryTicketIsEphemeralBoundAndSingleUse(t *testing.T) {
	if StoreRecoveryTicket("", "secret", time.Now().Add(time.Minute)) ||
		StoreRecoveryTicket("old", "secret", time.Now().Add(-time.Second)) {
		t.Fatal("invalid ticket accepted")
	}
	if !StoreRecoveryTicket("task-a", "private-ticket", time.Now().Add(time.Minute)) {
		t.Fatal("valid ticket rejected")
	}
	if !StoreRecoveryTicket("task-a", "private-ticket", time.Now().Add(time.Minute)) {
		t.Fatal("same ticket reconciliation was rejected")
	}
	if StoreRecoveryTicket("task-a", "replacement", time.Now().Add(time.Minute)) {
		t.Fatal("existing binding overwritten")
	}
	if _, ok := TakeRecoveryTicket("task-b"); ok {
		t.Fatal("different task accessed ticket")
	}
	if value, ok := TakeRecoveryTicket("task-a"); !ok || value != "private-ticket" {
		t.Fatal("exact task did not receive ticket")
	}
	if _, ok := TakeRecoveryTicket("task-a"); ok {
		t.Fatal("ticket replayed")
	}
}
