package usecase

import (
	"os"
	"testing"

	"mindfs/server/internal/agent"
	"mindfs/server/internal/session"
)

type rccModelRegistry struct {
	*commandTestRegistry
	prober *agent.Prober
}

func TestRCCEffortDefaultsAndResumedSelection(t *testing.T) {
	command, _ := os.Executable()
	cfg := agent.Config{Agents: []agent.Definition{{Name: "remote-profile", Protocol: agent.ProtocolRCC, Command: command}}}
	s := Service{Registry: &rccModelRegistry{commandTestRegistry: &commandTestRegistry{}, prober: agent.NewProber(&cfg, nil, 0)}}
	for _, tc := range []struct{ model, explicit, previous, want string }{
		{"", "", "", "high"}, {"opus", "", "", "high"},
		{"opus", "low", "", "low"}, {"opus", "", "max", "max"},
		{"opus", "medium", "max", "medium"},
	} {
		t.Run(tc.model+"/"+tc.explicit+"/"+tc.previous, func(t *testing.T) {
			in := SendMessageInput{Agent: "remote-profile", Model: tc.model, Effort: tc.explicit}
			current := &session.Session{Exchanges: []session.Exchange{{Effort: tc.previous}}}
			s.applyMessageRuntimeDefaults(&in, current)
			if in.Effort != tc.want || in.Model != tc.model {
				t.Fatalf("resolved model/effort = %q/%q, want %q/%q", in.Model, in.Effort, tc.model, tc.want)
			}
		})
	}
	other := SendMessageInput{Agent: "claude", Model: "opus"}
	applyMessageRuntimeDefaultsFromStatus(&other, agent.Status{Protocol: agent.ProtocolClaudeSDK, DefaultEffort: "high"}, true)
	if other.Effort != "" {
		t.Fatal("changed non-RCC explicit-model default semantics")
	}
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
