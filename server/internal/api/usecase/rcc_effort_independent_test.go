//go:build linux

package usecase

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"mindfs/server/internal/agent"
	rootfs "mindfs/server/internal/fs"
	"mindfs/server/internal/session"
)

func TestRCCEffortIndependentUsecaseReopenResume(t *testing.T) {
	root := t.TempDir()
	command, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	capture := filepath.Join(root, "effort-wire")
	cfg := agent.Config{Agents: []agent.Definition{{Name: "remote-effort", Protocol: agent.ProtocolRCC, Command: command, Args: []string{"-test.run=^TestRCCModelsIndependentWireHelper$"}, Env: map[string]string{"MINDFS_RCC_INDEPENDENT_MODEL_HELPER": "1", "MINDFS_RCC_INDEPENDENT_MODEL_CAPTURE": capture}}}}
	pool := agent.NewPool(cfg)
	defer pool.CloseAll()
	service := Service{Registry: &rccModelRegistry{commandTestRegistry: &commandTestRegistry{}, prober: agent.NewProber(&cfg, nil, 0)}}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	manager := session.NewManager(rootfs.NewRootInfo("fixture", "fixture", root))
	current, err := manager.Create(ctx, session.CreateInput{Type: session.TypeChat, Agent: "remote-effort", Name: "Effort"})
	if err != nil {
		t.Fatal(err)
	}
	if err := manager.UpsertAgentBinding(ctx, session.AgentBinding{SessionKey: current.Key, Agent: "remote-effort", AgentSessionID: "independent-resume"}); err != nil {
		t.Fatal(err)
	}
	var previous interface{}
	for _, effort := range []string{"high", "low", "medium", "xhigh", "max"} {
		in := SendMessageInput{Agent: "remote-effort", Model: "opus"}
		if effort != "high" {
			in.Effort = effort
		}
		service.applyMessageRuntimeDefaults(&in, current)
		if in.Effort != effort {
			t.Fatalf("default/explicit effort=%q want %q", in.Effort, effort)
		}
		live, _, err := service.ensureAgentSession(ctx, pool, manager, current, "remote-effort", in.Model, "", in.Effort, "", root, "")
		if err != nil {
			t.Fatal(err)
		}
		if previous == live {
			t.Fatal("effort change reused runtime")
		}
		previous = live
		raw, err := os.ReadFile(capture)
		if err != nil {
			t.Fatal(err)
		}
		for _, want := range []string{"--effort\n" + effort, "--resume\nindependent-resume", "--model\nopus"} {
			if !strings.Contains(string(raw), want) {
				t.Fatalf("argv missing %q: %q", want, raw)
			}
		}
		current.Exchanges = []session.Exchange{{Effort: effort}}
		current.Model = "opus"
		retained := SendMessageInput{Agent: "remote-effort", Model: "fable"}
		service.applyMessageRuntimeDefaults(&retained, current)
		if retained.Effort != effort {
			t.Fatalf("resume lost %q: %q", effort, retained.Effort)
		}
	}
}
