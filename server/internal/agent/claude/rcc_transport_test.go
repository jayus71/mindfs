//go:build linux

package claude

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"reflect"
	"strings"
	"syscall"
	"testing"
	"time"
)

// This process speaks the real SDK wire protocol through actual OS pipes. It
// acts as RCC's transparent stdio boundary, without network or credentials.
func TestRCCProcessHelper(t *testing.T) {
	if os.Getenv("MINDFS_RCC_HELPER") != "1" {
		return
	}
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGTERM)
	go func() {
		<-sig
		if os.Getenv("MINDFS_RCC_SLOW_STOP") == "1" {
			time.Sleep(6 * time.Second)
		}
		_ = os.WriteFile(os.Getenv("MINDFS_RCC_SIGNAL"), []byte("SIGTERM"), 0600)
		os.Exit(0)
	}()
	cwd, _ := os.Getwd()
	capture, _ := json.Marshal(map[string]any{"args": os.Args[1:], "cwd": cwd, "env": os.Getenv("MINDFS_RCC_MARKER")})
	_ = os.WriteFile(os.Getenv("MINDFS_RCC_CAPTURE"), capture, 0600)
	if os.Getenv("MINDFS_RCC_FAIL_INIT") == "1" {
		fmt.Fprintln(os.Stderr, "run rcc login before opening this project")
		os.Exit(23)
	}
	emit := func(v any) { b, _ := json.Marshal(v); fmt.Println(string(b)) }
	result := func(text string) {
		emit(map[string]any{"type": "result", "subtype": "success", "session_id": "remote-session", "result": text, "is_error": false, "num_turns": 1, "duration_ms": 1, "duration_api_ms": 1})
	}
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		var msg map[string]any
		_ = json.Unmarshal(scanner.Bytes(), &msg)
		switch msg["type"] {
		case "control_request":
			req, _ := msg["request"].(map[string]any)
			emit(map[string]any{"type": "control_response", "response": map[string]any{"subtype": "success", "request_id": msg["request_id"], "response": map[string]any{}}})
			if req["subtype"] == "initialize" {
				emit(map[string]any{"type": "system", "subtype": "init", "session_id": "remote-session"})
			}
			if req["subtype"] == "interrupt" {
				result("interrupted")
			}
		case "user":
			m, _ := msg["message"].(map[string]any)
			content, _ := m["content"].(string)
			if blocks, ok := m["content"].([]any); ok {
				for _, block := range blocks {
					if item, ok := block.(map[string]any); ok {
						if text, ok := item["text"].(string); ok {
							content += text
						}
					}
				}
			}
			switch content {
			case "exit":
				fmt.Fprintln(os.Stderr, "remote project already has an active session")
				os.Exit(23)
			case "hold":
				// Keep stdin alive so close must deliver SIGTERM.
			case "permission":
				emit(map[string]any{"type": "control_request", "request_id": "remote-permission", "request": map[string]any{"subtype": "can_use_tool", "tool_name": "Read", "input": map[string]any{"file_path": "example"}, "tool_use_id": "read-1"}})
			default:
				result(content)
			}
		case "control_response":
			response, _ := msg["response"].(map[string]any)
			if response["request_id"] == "remote-permission" {
				result("permission roundtrip")
			}
		}
	}
	// RCC may retain a remote session after EOF. The adapter must signal it.
	select {}
}

func rccTestOptions(t *testing.T) OpenOptions {
	t.Helper()
	command, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	return OpenOptions{RCC: true, AgentName: "rcc", SessionKey: "rcc-test", RootPath: root,
		Command: command, Args: []string{"-test.run=^TestRCCProcessHelper$"}, Env: map[string]string{
			"MINDFS_RCC_HELPER": "1", "MINDFS_RCC_CAPTURE": filepath.Join(root, "capture.json"),
			"MINDFS_RCC_SIGNAL": filepath.Join(root, "signal"), "MINDFS_RCC_MARKER": "isolated",
		}}
}

func TestRCCSDKProcessRoundtripAndResume(t *testing.T) {
	opts := rccTestOptions(t)
	opts.ResumeSessionID = "remote-history-id"
	opts.DeveloperInstructions = "keep instructions separate"
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	sess, err := NewRuntime().OpenSession(ctx, opts)
	if err != nil {
		t.Fatal(err)
	}
	defer sess.Close()
	for _, message := range []string{"first turn", "second turn", "permission"} {
		if err := sess.SendMessage(ctx, message); err != nil {
			t.Fatal(err)
		}
	}
	if sess.SessionID() != "remote-session" {
		t.Fatalf("session ID = %q", sess.SessionID())
	}
	if err := sess.SetModel(ctx, "remote-model"); err != nil {
		t.Fatal(err)
	}
	if err := sess.SetPlanMode(ctx, true); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(opts.Env["MINDFS_RCC_CAPTURE"])
	if err != nil {
		t.Fatal(err)
	}
	var capture struct {
		Args []string
		Cwd  string
		Env  string
	}
	if err := json.Unmarshal(raw, &capture); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(capture.Args[:3], []string{"-test.run=^TestRCCProcessHelper$", "--", "-p"}) {
		t.Fatalf("argv = %#v", capture.Args)
	}
	for _, pair := range [][2]string{{"--input-format", "stream-json"}, {"--output-format", "stream-json"}, {"--resume", "remote-history-id"}, {"--append-system-prompt", opts.DeveloperInstructions}} {
		found := false
		for i := 0; i+1 < len(capture.Args); i++ {
			if capture.Args[i] == pair[0] && capture.Args[i+1] == pair[1] {
				found = true
			}
		}
		if !found {
			t.Fatalf("missing %v in %v", pair, capture.Args)
		}
	}
	if capture.Cwd != opts.RootPath || capture.Env != "isolated" {
		t.Fatalf("capture = %+v", capture)
	}
	if err := sess.Close(); err != nil {
		t.Fatal(err)
	}
	if raw, err := os.ReadFile(opts.Env["MINDFS_RCC_SIGNAL"]); err != nil || string(raw) != "SIGTERM" {
		t.Fatalf("shutdown signal = %s, %v", raw, err)
	}
	// A new client resumes using a remote ID, without reading local history.
	sess, err = NewRuntime().OpenSession(ctx, opts)
	if err != nil {
		t.Fatal(err)
	}
	defer sess.Close()
	if err := sess.SendMessage(ctx, "after restart"); err != nil {
		t.Fatal(err)
	}
}

func TestRCCNonzeroExitPreserved(t *testing.T) {
	for _, initializing := range []bool{false, true} {
		t.Run(fmt.Sprint(initializing), func(t *testing.T) {
			opts := rccTestOptions(t)
			if initializing {
				opts.Env["MINDFS_RCC_FAIL_INIT"] = "1"
			}
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			sess, err := NewRuntime().OpenSession(ctx, opts)
			if err == nil {
				defer sess.Close()
				err = sess.SendMessage(ctx, "exit")
			}
			var exitErr *exec.ExitError
			if !errors.As(err, &exitErr) || exitErr.ExitCode() != 23 {
				t.Fatalf("error = %v, want exit 23", err)
			}
			if initializing && !strings.Contains(err.Error(), "rcc login") {
				t.Fatalf("missing startup diagnostic: %v", err)
			}
			if !initializing && !strings.Contains(err.Error(), "active session") {
				t.Fatalf("missing exit diagnostic: %v", err)
			}
		})
	}
}

func TestRCCShutdownAllowsRemoteCleanupBeyondFiveSeconds(t *testing.T) {
	opts := rccTestOptions(t)
	opts.Env["MINDFS_RCC_SLOW_STOP"] = "1"
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Second)
	defer cancel()
	sess, err := NewRuntime().OpenSession(ctx, opts)
	if err != nil {
		t.Fatal(err)
	}
	if err := sess.Close(); err != nil {
		t.Fatal(err)
	}
	if raw, err := os.ReadFile(opts.Env["MINDFS_RCC_SIGNAL"]); err != nil || string(raw) != "SIGTERM" {
		t.Fatalf("cleanup was killed prematurely: %s, %v", raw, err)
	}
}

func TestRCCStderrTailIsBounded(t *testing.T) {
	var tail rccStderrTail
	_, _ = tail.Write([]byte(strings.Repeat("a", 6000)))
	_, _ = tail.Write([]byte("login required"))
	if got := tail.String(); len(got) != 4096 || !strings.HasSuffix(got, "login required") {
		t.Fatalf("stderr tail length = %d", len(got))
	}
}

func TestRCCContextCancellationClosesClient(t *testing.T) {
	opts := rccTestOptions(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	sess, err := NewRuntime().OpenSession(ctx, opts)
	if err != nil {
		t.Fatal(err)
	}
	defer sess.Close()
	turnCtx, turnCancel := context.WithTimeout(ctx, 100*time.Millisecond)
	defer turnCancel()
	if err := sess.SendMessage(turnCtx, "hold"); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("cancel = %v", err)
	}
	if raw, err := os.ReadFile(opts.Env["MINDFS_RCC_SIGNAL"]); err != nil || string(raw) != "SIGTERM" {
		t.Fatalf("shutdown signal = %s, %v", raw, err)
	}
}

func TestRCCRejectsLocalForkAndArgumentSeparator(t *testing.T) {
	opts := rccTestOptions(t)
	opts.ForkSessionID, opts.ResumeMessageID = "remote", "uuid"
	if _, err := NewRuntime().OpenSession(context.Background(), opts); err == nil || !strings.Contains(err.Error(), "fork") {
		t.Fatalf("fork = %v", err)
	}
	opts.ForkSessionID, opts.ResumeMessageID = "", ""
	opts.Args = []string{"--"}
	if _, err := NewRuntime().OpenSession(context.Background(), opts); err == nil {
		t.Fatal("accepted separator")
	}
}
