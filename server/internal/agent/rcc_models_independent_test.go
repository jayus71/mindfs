//go:build linux

package agent

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	agenttypes "mindfs/server/internal/agent/types"
)

// Check the public Pool input boundary, rather than constructing SDK options.
func TestRCCModelsIndependentPoolAliasesAndResume(t *testing.T) {
	for _, model := range []string{"", "sonnet", "opus", "fable"} {
		t.Run("model="+model, func(t *testing.T) {
			root := t.TempDir()
			command, err := os.Executable()
			if err != nil {
				t.Fatal(err)
			}
			capture := filepath.Join(root, "argv")
			pool := NewPool(Config{Agents: []Definition{{Name: "remote-alias-profile", Command: command, Protocol: ProtocolRCC,
				Args: []string{"-test.run=^TestRCCPoolProcessHelper$"}, Env: map[string]string{"MINDFS_RCC_POOL_HELPER": "1", "MINDFS_RCC_POOL_CAPTURE": capture}}}})
			defer pool.CloseAll()
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			in := agenttypes.OpenSessionInput{SessionKey: "alias-check", AgentName: "remote-alias-profile", Model: model, RootPath: root}
			for _, resume := range []string{"", "remote-history-independent"} {
				in.AgentSessionID = resume
				sess, err := pool.GetOrCreate(ctx, in)
				if err != nil {
					t.Fatal(err)
				}
				if err := sess.SendMessage(ctx, "isolated alias verification"); err != nil {
					t.Fatal(err)
				}
				raw, err := os.ReadFile(capture)
				if err != nil {
					t.Fatal(err)
				}
				args := strings.Split(string(raw), "\n")
				flags := map[string]string{}
				for i := 0; i+1 < len(args); i++ {
					if strings.HasPrefix(args[i], "--") {
						flags[args[i]] = args[i+1]
					}
				}
				if model == "" {
					if _, exists := flags["--model"]; exists {
						t.Fatalf("empty model overridden: %q", raw)
					}
				} else if flags["--model"] != model {
					t.Fatalf("model = %q; want %q", flags["--model"], model)
				}
				if flags["--resume"] != resume {
					t.Fatalf("resume = %q; want %q", flags["--resume"], resume)
				}
				if _, exists := flags["--effort"]; exists {
					t.Fatalf("alias inferred effort: %q", raw)
				}
				pool.Close(in.SessionKey)
			}
		})
	}
}
