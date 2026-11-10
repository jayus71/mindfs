//go:build linux

package agent

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	agenttypes "mindfs/server/internal/agent/types"
)

func TestRCCPoolProcessHelper(t *testing.T) {
	if os.Getenv("MINDFS_RCC_POOL_HELPER") != "1" {
		return
	}
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGTERM)
	go func() { <-sig; os.Exit(0) }()
	_ = os.WriteFile(os.Getenv("MINDFS_RCC_POOL_CAPTURE"), []byte(strings.Join(os.Args[1:], "\n")), 0600)
	emit := func(v any) { b, _ := json.Marshal(v); fmt.Println(string(b)) }
	scan := bufio.NewScanner(os.Stdin)
	for scan.Scan() {
		var m struct {
			Type      string `json:"type"`
			RequestID string `json:"request_id"`
			Message   struct {
				Content []struct {
					Text string `json:"text"`
				} `json:"content"`
			} `json:"message"`
		}
		_ = json.Unmarshal(scan.Bytes(), &m)
		if m.Type == "control_request" {
			emit(map[string]any{"type": "control_response", "response": map[string]any{"subtype": "success", "request_id": m.RequestID, "response": map[string]any{}}})
			emit(map[string]any{"type": "system", "subtype": "init", "session_id": "pool-remote-id"})
		}
		if m.Type == "user" && len(m.Message.Content) > 0 {
			content := m.Message.Content[0].Text
			if content == "exit" {
				os.Exit(23)
			}
			if content != "hold" {
				emit(map[string]any{"type": "result", "subtype": "success", "session_id": "pool-remote-id", "result": content})
			}
		}
	}
	select {}
}

func TestRCCPoolReopensAfterCancellationAndExit(t *testing.T) {
	for _, failure := range []string{"context", "cancel", "exit"} {
		t.Run(failure, func(t *testing.T) {
			root := t.TempDir()
			command, _ := os.Executable()
			capture := filepath.Join(root, "argv")
			pool := NewPool(Config{Agents: []Definition{{Name: "rcc", Command: command, Protocol: ProtocolRCC, Args: []string{"-test.run=^TestRCCPoolProcessHelper$"}, Env: map[string]string{"MINDFS_RCC_POOL_HELPER": "1", "MINDFS_RCC_POOL_CAPTURE": capture}}}})
			defer pool.CloseAll()
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			in := agenttypes.OpenSessionInput{SessionKey: "same-key", AgentName: "rcc", RootPath: root}
			sess, err := pool.GetOrCreate(ctx, in)
			if err != nil {
				t.Fatal(err)
			}
			if err := sess.SendMessage(ctx, "first"); err != nil {
				t.Fatal(err)
			}
			in.AgentSessionID = sess.SessionID()
			if failure == "exit" {
				if err := sess.SendMessage(ctx, "exit"); err == nil {
					t.Fatal("exit accepted")
				}
			} else if failure == "context" {
				turnCtx, turnCancel := context.WithTimeout(ctx, 100*time.Millisecond)
				err = sess.SendMessage(turnCtx, "hold")
				turnCancel()
				if !errors.Is(err, context.DeadlineExceeded) {
					t.Fatalf("context cancellation = %v", err)
				}
			} else {
				done := make(chan error, 1)
				go func() { done <- sess.SendMessage(ctx, "hold") }()
				if err := sess.CancelCurrentTurn(); err != nil {
					t.Fatal(err)
				}
				if err := <-done; err == nil {
					t.Fatal("canceled turn returned success")
				}
			}
			if _, ok := pool.Get(in.SessionKey); ok {
				t.Fatal("disconnected handle remained in pool")
			}
			next, err := pool.GetOrCreate(ctx, in)
			if err != nil {
				t.Fatal(err)
			}
			if err := next.SendMessage(ctx, "after failure"); err != nil {
				t.Fatal(err)
			}
			raw, err := os.ReadFile(capture)
			if err != nil || !strings.Contains(string(raw), "--resume\npool-remote-id") {
				t.Fatalf("resume argv = %s, %v", raw, err)
			}
		})
	}
}

func TestRCCProbeOnlyChecksInstallationAndRejectsLocalHistory(t *testing.T) {
	command, _ := os.Executable()
	def := Definition{Name: "rcc", Command: command, Protocol: ProtocolRCC, Args: []string{"--invalid-no-session-must-start"}}
	st := probeConfiguredAgentWithPool(context.Background(), "rcc", def, nil, nil, probePhaseInitial)
	if !st.Available || !st.Installed || st.ProbeError != "" {
		t.Fatalf("installation status = %+v", st)
	}
	if len(st.Models) != 3 || st.Models[0].ID != "sonnet" || st.Models[1].ID != "opus" || st.Models[2].ID != "fable" {
		t.Fatalf("runtime aliases = %+v", st.Models)
	}
	for _, model := range st.Models {
		if model.SupportEffort || len(model.Efforts) != 0 || !strings.Contains(model.Description, "运行端") {
			t.Fatalf("alias advertised unverified capabilities: %+v", model)
		}
	}
	if st.DefaultModelID != "" || st.CurrentModelID != "" || st.DefaultEffort != "high" || strings.Join(st.Efforts, ",") != "low,medium,high,xhigh,max" {
		t.Fatalf("probe inferred remote defaults: %+v", st)
	}
	if _, err := NewExternalSessionImporter(def); err == nil || !strings.Contains(err.Error(), "remote history") {
		t.Fatalf("importer = %v", err)
	}
	pool := NewPool(Config{Agents: []Definition{def}})
	defer pool.CloseAll()
	if !pool.SupportsDeveloperInstructions("rcc") {
		t.Fatal("RCC lost developer instructions")
	}
	if _, err := pool.GetOrCreate(context.Background(), agenttypes.OpenSessionInput{SessionKey: "probe", AgentName: "rcc", Probe: true}); err == nil {
		t.Fatal("runtime probe opened a project")
	}
}
