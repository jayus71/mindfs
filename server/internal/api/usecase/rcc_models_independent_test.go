//go:build linux

package usecase

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"mindfs/server/internal/agent"
	"mindfs/server/internal/session"
)

func TestRCCModelsIndependentWireHelper(t *testing.T) {
	if os.Getenv("MINDFS_RCC_INDEPENDENT_MODEL_HELPER") != "1" {
		return
	}
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGTERM)
	go func() { <-sig; os.Exit(0) }()
	base := os.Getenv("MINDFS_RCC_INDEPENDENT_MODEL_CAPTURE")
	_ = os.WriteFile(base, []byte(strings.Join(os.Args[1:], "\n")), 0600)
	scan := bufio.NewScanner(os.Stdin)
	for scan.Scan() {
		var m map[string]any
		_ = json.Unmarshal(scan.Bytes(), &m)
		if m["type"] != "control_request" {
			continue
		}
		req, _ := m["request"].(map[string]any)
		if req["subtype"] == "set_model" {
			_ = os.WriteFile(base+".model", []byte(fmt.Sprint(req["model"])), 0600)
		}
		b, _ := json.Marshal(map[string]any{"type": "control_response", "response": map[string]any{"subtype": "success", "request_id": m["request_id"], "response": map[string]any{}}})
		fmt.Println(string(b))
	}
	select {}
}

func TestRCCModelsIndependentUsecaseToSDK(t *testing.T) {
	root := t.TempDir()
	command, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	capture := filepath.Join(root, "wire")
	cfg := agent.Config{Agents: []agent.Definition{{Name: "remote-profile", Protocol: agent.ProtocolRCC, Command: command,
		Args: []string{"-test.run=^TestRCCModelsIndependentWireHelper$"}, Env: map[string]string{"MINDFS_RCC_INDEPENDENT_MODEL_HELPER": "1", "MINDFS_RCC_INDEPENDENT_MODEL_CAPTURE": capture}}}}
	pool := agent.NewPool(cfg)
	defer pool.CloseAll()
	s := Service{Registry: &rccModelRegistry{commandTestRegistry: &commandTestRegistry{}, prober: agent.NewProber(&cfg, nil, 0)}}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	current := &session.Session{Key: "independent-model"}
	first, _, err := s.ensureAgentSession(ctx, pool, nil, current, "remote-profile", "sonnet", "", "", "", root, "")
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(capture)
	if err != nil || !strings.Contains(string(raw), "--model\nsonnet") {
		t.Fatalf("initial argv %q, %v", raw, err)
	}
	current.Model = "sonnet"
	next, _, err := s.ensureAgentSession(ctx, pool, nil, current, "remote-profile", "opus", "", "", "", root, "")
	if err != nil || first != next {
		t.Fatalf("live switch reopened session: %v", err)
	}
	raw, err = os.ReadFile(capture + ".model")
	if err != nil || string(raw) != "opus" {
		t.Fatalf("live model control %q, %v", raw, err)
	}
	current.Model = "opus"
	next, _, err = s.ensureAgentSession(ctx, pool, nil, current, "remote-profile", "", "", "", "", root, "")
	if err != nil || first != next || next.CurrentModel() != "opus" {
		t.Fatalf("empty existing model = %v, %v", next, err)
	}
	raw, err = os.ReadFile(capture + ".model")
	if err != nil || string(raw) != "opus" {
		t.Fatalf("empty selection changed live model %q, %v", raw, err)
	}
}
