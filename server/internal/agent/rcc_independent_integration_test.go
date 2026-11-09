//go:build linux

package agent

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	agenttypes "mindfs/server/internal/agent/types"
)

// This opt-in test uses an actual RCC executable and the private two-VM fixture.
// No production account, provider, or local Claude transcript is used.
func TestRCCIndependentActualIntegration(t *testing.T) {
	root := os.Getenv("RCC_INDEPENDENT_STATE")
	if root == "" {
		t.Skip("requires private isolated RCC fixture")
	}
	scenario := os.Getenv("RCC_INDEPENDENT_SCENARIO")
	binary := os.Getenv("RCC_INDEPENDENT_BINARY")
	project := filepath.Join(root, "projects/alice/project-b")
	baseArgs := []string{"--profile", filepath.Join(root, "client-profile.json"), "--client-state", filepath.Join(root, "client-alice"), "--node", "node-alice", "--confirm-project"}
	def := Definition{Name: "rcc-independent", Protocol: Protocol("rcc"), Command: binary, Args: baseArgs,
		Env: map[string]string{"HOME": filepath.Join(root, "client-home"), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}}
	pool := NewPool(Config{Agents: []Definition{def}})
	defer pool.CloseAll()
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	defer cancel()
	in := agenttypes.OpenSessionInput{AgentName: def.Name, SessionKey: "independent-" + scenario, RootPath: project, Model: "claude-sonnet-4-6"}
	if scenario == "invalid" {
		def.Args = append(def.Args, "--independent-invalid-rcc-option")
		badPool := NewPool(Config{Agents: []Definition{def}})
		defer badPool.CloseAll()
		_, openErr := badPool.GetOrCreate(ctx, in)
		var exited *exec.ExitError
		if !errors.As(openErr, &exited) || exited.ExitCode() == 0 {
			t.Fatalf("actual RCC invalid flag lost exit status: %v", openErr)
		}
		if !strings.Contains(openErr.Error(), "客户端参数无效") {
			t.Fatalf("actual RCC stderr diagnostic missing: %v", openErr)
		}
		t.Logf("actual RCC invalid-option exit preserved: %d", exited.ExitCode())
		return
	}
	idFile := filepath.Join(root, "independent-official-session")
	if scenario == "resume" {
		b, e := os.ReadFile(idFile)
		if e != nil {
			t.Fatal(e)
		}
		in.AgentSessionID = strings.TrimSpace(string(b))
	}
	listArgs := []string{"list", "--profile", filepath.Join(root, "client-profile.json"), "--client-state", filepath.Join(root, "client-alice")}
	knownBefore := map[string]bool{}
	for _, row := range independentRCCList(t, ctx, binary, listArgs, project) {
		knownBefore[row.ID] = true
	}
	ownedIDs := map[string]bool{}
	captureNew := func() {
		for _, row := range independentRCCList(t, ctx, binary, listArgs, project) {
			if !knownBefore[row.ID] && row.Node == "node-alice" {
				ownedIDs[row.ID] = true
				t.Logf("owned RCC native session=%s project=%s node=%s", row.ID, row.Project, row.Node)
			}
		}
		if len(ownedIDs) == 0 {
			t.Fatal("no new RCC native session owned by this case")
		}
	}
	awaitStopped := func() {
		deadline := time.Now().Add(20 * time.Second)
		start := time.Now()
		for {
			found := map[string]bool{}
			states := map[string]string{}
			complete := true
			for _, row := range independentRCCList(t, ctx, binary, listArgs, project) {
				if ownedIDs[row.ID] {
					found[row.ID] = true
					states[row.ID] = row.State + "/" + row.Remote
					if row.State != "stopped" || row.Remote != "stopped" {
						complete = false
					}
				}
			}
			for id := range ownedIDs {
				if !found[id] {
					complete = false
				}
			}
			if complete {
				t.Logf("confirmed owned native sessions stopped elapsed=%s states=%v", time.Since(start), states)
				return
			}
			if time.Now().After(deadline) {
				t.Fatalf("owned RCC session stop was not confirmed within 20s: %v", states)
			}
			time.Sleep(200 * time.Millisecond)
		}
	}
	sess, err := pool.GetOrCreate(ctx, in)
	if err != nil {
		t.Fatalf("actual RCC initialize/control handshake: %v", err)
	}
	captureNew()
	var mu sync.Mutex
	chunks, questions := 0, 0
	var allowAnswer atomic.Bool
	allowAnswer.Store(scenario != "cancel-resume" && scenario != "cancel-api")
	questionReached := make(chan struct{}, 1)
	sess.OnUpdate(func(e agenttypes.Event) {
		mu.Lock()
		defer mu.Unlock()
		if e.Type == agenttypes.EventTypeMessageChunk {
			chunks++
		}
		if call, ok := e.Data.(agenttypes.ToolCall); ok && call.Kind == agenttypes.ToolKindAskUser && call.Meta["toolUseId"] == call.CallID && call.Status == "running" && e.Type == agenttypes.EventTypeToolCall {
			questions++
			select {
			case questionReached <- struct{}{}:
			default:
			}
			if !allowAnswer.Load() {
				return
			}
			go func() {
				if err := sess.AnswerQuestion(ctx, agenttypes.AskUserAnswer{ToolUseID: call.CallID, Answers: map[string]string{"Pick a color?": "Blue"}}); err != nil {
					t.Errorf("answer question: %v", err)
				}
			}()
		}
	})
	if err = sess.SetModel(ctx, "claude-sonnet-4-6"); err != nil {
		t.Fatalf("set_model control request: %v", err)
	}
	if scenario == "cancel-resume" || scenario == "cancel-api" {
		turnCtx, turnCancel := context.WithCancel(ctx)
		done := make(chan error, 1)
		go func() { done <- sess.SendMessage(turnCtx, "MINDFS_RCC_CANCEL_PENDING") }()
		select {
		case <-questionReached:
		case <-ctx.Done():
			t.Fatal("no pending question before cancellation")
		}
		id := sess.SessionID()
		if scenario == "cancel-api" {
			if err = sess.CancelCurrentTurn(); err != nil {
				t.Fatalf("CancelCurrentTurn: %v", err)
			}
		} else {
			turnCancel()
		}
		defer turnCancel()
		if err = <-done; !errors.Is(err, context.Canceled) {
			t.Fatalf("turn cancellation: %v", err)
		}
		awaitStopped()
		allowAnswer.Store(true)
		in.AgentSessionID = id
		next, e := pool.GetOrCreate(ctx, in)
		if e != nil {
			t.Fatalf("reopen cancelled session: %v", e)
		}
		captureNew()
		next.OnUpdate(func(e agenttypes.Event) {
			if call, ok := e.Data.(agenttypes.ToolCall); ok && call.Kind == agenttypes.ToolKindAskUser && call.Meta["toolUseId"] == call.CallID && e.Type == agenttypes.EventTypeToolCall {
				go next.AnswerQuestion(ctx, agenttypes.AskUserAnswer{ToolUseID: call.CallID, Answers: map[string]string{"Pick a color?": "Blue"}})
			}
		})
		if e = next.SendMessage(ctx, "MINDFS_RCC_CANCEL_RESUMED"); e != nil {
			t.Fatalf("same-key send after cancelled turn: %v", e)
		}
		if next.SessionID() != id {
			t.Fatalf("cancel-resume conversation changed: %s -> %s", id, next.SessionID())
		}
		sess = next
		t.Logf("same-key turn cancellation and remote resume passed: %s", id)
	} else if scenario == "terminate" {
		pidder, ok := sess.(interface{ ProcessID() int })
		if !ok || pidder.ProcessID() == 0 {
			t.Fatal("RCC process PID unavailable")
		}
		start := time.Now()
		if err = syscall.Kill(pidder.ProcessID(), syscall.SIGTERM); err != nil {
			t.Fatal(err)
		}
		deadline := time.Now().Add(20 * time.Second)
		for syscall.Kill(pidder.ProcessID(), 0) == nil && time.Now().Before(deadline) {
			time.Sleep(100 * time.Millisecond)
		}
		if syscall.Kill(pidder.ProcessID(), 0) == nil {
			t.Fatal("SIGTERM did not exit within 20 seconds")
		}
		t.Logf("SIGTERM bounded exit elapsed=%s", time.Since(start))
	} else {
		if err = sess.SendMessage(ctx, "MINDFS_RCC_"+scenario+"_FIRST"); err != nil {
			t.Fatalf("first user turn: %v", err)
		}
		if scenario == "basic" {
			if err = sess.SendMessage(ctx, "MINDFS_RCC_BASIC_SECOND"); err != nil {
				t.Fatalf("second user turn: %v", err)
			}
			if sess.SessionID() == "" {
				t.Fatal("official remote conversation ID missing")
			}
			if err = os.WriteFile(idFile, []byte(sess.SessionID()), 0600); err != nil {
				t.Fatal(err)
			}
		}
		if scenario == "resume" && sess.SessionID() != in.AgentSessionID {
			t.Fatalf("resume changed remote conversation ID: %s", sess.SessionID())
		}
		mu.Lock()
		q, c := questions, chunks
		mu.Unlock()
		if c == 0 {
			t.Fatal("no normalized assistant message chunks")
		}
		if scenario == "question" && q == 0 {
			t.Fatal("AskUserQuestion callback did not reach MindFS")
		}
		t.Logf("scenario=%s remote_conversation=%s message_chunks=%d questions=%d", scenario, sess.SessionID(), c, q)
	}
	start := time.Now()
	if err = sess.Close(); err != nil {
		t.Logf("close returned: %v", err)
	}
	if time.Since(start) > 20*time.Second {
		t.Fatal("session close exceeded 20 seconds")
	}
	awaitStopped()
}

type independentRCCSession struct{ ID, Project, Node, State, Remote string }

func independentRCCList(t *testing.T, ctx context.Context, binary string, args []string, project string) []independentRCCSession {
	t.Helper()
	cmd := exec.CommandContext(ctx, binary, args...)
	cmd.Dir = project
	out, err := cmd.Output()
	if err != nil {
		t.Fatalf("RCC list: %v", err)
	}
	var listed struct{ Sessions []independentRCCSession }
	if err = json.Unmarshal(out, &listed); err != nil {
		t.Fatalf("RCC list JSON: %v", err)
	}
	return listed.Sessions
}
