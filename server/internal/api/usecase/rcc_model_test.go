package usecase

import (
	"os"
	"testing"

	"mindfs/server/internal/agent"
)

type rccModelRegistry struct {
	*commandTestRegistry
	prober *agent.Prober
}

func (r *rccModelRegistry) GetProber() *agent.Prober { return r.prober }

func TestRCCAliasMenuDoesNotRejectFullModelIDs(t *testing.T) {
	command, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	cfg := agent.Config{Agents: []agent.Definition{{Name: "remote-profile", Protocol: agent.ProtocolRCC, Command: command}}}
	s := Service{Registry: &rccModelRegistry{commandTestRegistry: &commandTestRegistry{}, prober: agent.NewProber(&cfg, nil, 0)}}
	for _, model := range []string{"", "sonnet", "claude-runtime-specific-id"} {
		if err := s.validateAgentModel("remote-profile", model); err != nil {
			t.Fatalf("runtime must validate %q: %v", model, err)
		}
	}
}

func TestRCCEffortChangesReopenRuntime(t *testing.T) {
	pool := agent.NewPool(agent.Config{Agents: []agent.Definition{{Name: "remote-profile", Protocol: agent.ProtocolRCC, Command: "rcc"}}})
	defer pool.CloseAll()
	if !shouldReopenSessionForSetting(pool, "remote-profile", "high", "low") {
		t.Fatal("RCC effort change must reopen and resume with new CLI options")
	}
	if shouldReopenSessionForSetting(pool, "remote-profile", "high", "high") {
		t.Fatal("unchanged effort must preserve the live session")
	}
}
