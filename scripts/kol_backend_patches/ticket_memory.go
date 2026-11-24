package stream

import (
	"sync"
	"time"
)

// A recovery ticket is intentionally process-local. A backend restart drops it
// and forces a fresh, independently verified observation before any resume.
type recoveryTicket struct {
	url       string
	expiresAt time.Time
}

var recoveryTickets = struct {
	sync.Mutex
	items map[string]recoveryTicket
}{items: make(map[string]recoveryTicket)}

func StoreRecoveryTicket(binding, value string, expiresAt time.Time) bool {
	if binding == "" || value == "" || !expiresAt.After(time.Now()) {
		return false
	}
	recoveryTickets.Lock()
	defer recoveryTickets.Unlock()
	if prior, exists := recoveryTickets.items[binding]; exists {
		// Repeated preparation may reconcile the same in-memory ticket, but
		// must never replace it with a different provider effect.
		return prior.url == value && prior.expiresAt.After(time.Now())
	}
	recoveryTickets.items[binding] = recoveryTicket{url: value, expiresAt: expiresAt}
	return true
}

// Take returns one ticket once; expired or missing tickets fail closed.
func TakeRecoveryTicket(binding string) (string, bool) {
	recoveryTickets.Lock()
	defer recoveryTickets.Unlock()
	ticket, ok := recoveryTickets.items[binding]
	delete(recoveryTickets.items, binding)
	if !ok || !ticket.expiresAt.After(time.Now()) {
		return "", false
	}
	return ticket.url, true
}
