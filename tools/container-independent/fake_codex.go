// Fake Codex app-server for isolated container verification. No network calls.
package main
import("bufio";"crypto/sha256";"encoding/hex";"encoding/json";"fmt";"os";"path/filepath";"strings";"sync";"time")
var output sync.Mutex
var logMu sync.Mutex
var logPath string
func emit(v any){output.Lock();defer output.Unlock();b,_:=json.Marshal(v);fmt.Println(string(b))}
func logEntry(kind string,data map[string]any){logMu.Lock();defer logMu.Unlock();data["kind"]=kind;data["pid"]=os.Getpid();data["at"]=time.Now().UTC().Format(time.RFC3339Nano);b,_:=json.Marshal(data);f,e:=os.OpenFile(logPath,os.O_CREATE|os.O_APPEND|os.O_WRONLY,0600);if e!=nil{panic(e)};defer f.Close();f.Write(append(b,'\n'))}
func main(){
 for _,arg:=range os.Args[1:]{if arg=="--version"{fmt.Println("codex-cli 0.0.0-container-independent-fixture");return}}
 home:=os.Getenv("HOME");if _,e:=os.Stat(filepath.Join(home,".independent-fixture-owned"));e!=nil{panic("fixture marker missing; refusing to read HOME")}
 logPath=os.Getenv("INDEPENDENT_CODEX_LOG");if logPath==""{panic("fixture log path missing")};ch:=os.Getenv("CODEX_HOME");if ch==""{ch=filepath.Join(home,".codex")};b,_:=os.ReadFile(filepath.Join(ch,"config.toml"));config:=string(b);digest:=sha256.Sum256(b);cwd,_:=os.Getwd()
 logEntry("start",map[string]any{"argv":os.Args,"home":home,"codex_home":os.Getenv("CODEX_HOME"),"cwd":cwd,"config":config,"config_sha256":hex.EncodeToString(digest[:]),"fixture_env":os.Getenv("INDEPENDENT_FIXTURE_ENV")})
 scanner:=bufio.NewScanner(os.Stdin);scanner.Buffer(make([]byte,4096),4*1024*1024);turn:=0
 for scanner.Scan(){var req struct{ID *json.RawMessage `json:"id"`;Method string `json:"method"`;Params map[string]any `json:"params"`};if json.Unmarshal(scanner.Bytes(),&req)!=nil{continue};logEntry("rpc",map[string]any{"method":req.Method,"params":req.Params});if req.ID==nil{continue};var result any=map[string]any{}
 switch req.Method{
 case "initialize":result=map[string]any{"userAgent":"independent-container-fixture","platformFamily":"unix","platformOs":"linux"}
 case "model/list":result=map[string]any{"data":[]any{map[string]any{"id":"fixture-model","model":"fixture-model","displayName":"Fixture Codex","isDefault":true,"defaultReasoningEffort":"medium","supportedReasoningEfforts":[]any{map[string]any{"reasoningEffort":"medium","description":"fixture"}}}},"nextCursor":nil}
 case "thread/start","thread/resume":id,_:=req.Params["threadId"].(string);if id==""{id=fmt.Sprintf("fixture-%d-%d",os.Getpid(),turn)};result=map[string]any{"thread":map[string]any{"id":id,"turns":[]any{}}}
 case "turn/start":turn++;thread,_:=req.Params["threadId"].(string);tid:=fmt.Sprintf("turn-%d-%d",os.Getpid(),turn);result=map[string]any{"turn":map[string]any{"id":tid,"status":"inProgress","items":[]any{}}};provider:="provider-v1";if strings.Contains(config,"provider-v2"){provider="provider-v2"};text:=fmt.Sprintf("fixture-response %s %d",provider,turn)
 go func(){time.Sleep(50*time.Millisecond);emit(map[string]any{"method":"turn/started","params":map[string]any{"threadId":thread,"turn":map[string]any{"id":tid,"status":"inProgress"}}});emit(map[string]any{"method":"item/agentMessage/delta","params":map[string]any{"threadId":thread,"turnId":tid,"itemId":"message-"+tid,"delta":text}});emit(map[string]any{"method":"item/completed","params":map[string]any{"threadId":thread,"turnId":tid,"item":map[string]any{"id":"message-"+tid,"type":"agentMessage","text":text}}});emit(map[string]any{"method":"turn/completed","params":map[string]any{"threadId":thread,"turn":map[string]any{"id":tid,"status":"completed","items":[]any{}}}})}()
 case "config/read":result=map[string]any{"config":map[string]any{"model_provider":"fixture"},"origins":map[string]any{}}
 case "account/read":result=map[string]any{"account":nil,"requiresOpenaiAuth":false}
 case "thread/read":result=map[string]any{"thread":map[string]any{"id":req.Params["threadId"],"turns":[]any{}}}
 }
 emit(map[string]any{"id":*req.ID,"result":result})
 }
 logEntry("eof",map[string]any{})
}
