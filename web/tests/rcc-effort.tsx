import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { ActionBar } from "../src/components/ActionBar";
import { I18nProvider } from "../src/i18n";
import { bootstrapService } from "../src/services/bootstrap";
import { e2eeService } from "../src/services/e2ee";
import "../src/index.css";
bootstrapService.canUseProtectedAPI = () => true;
e2eeService.protectedFetch = (input, init) => fetch(input, init);
e2eeService.parseProtectedJSONResponse = response => response.json();
function Fixture() {
 const [sent, setSent] = useState("");
 const prior = new URLSearchParams(location.search).get("prior");
 return <I18nProvider><main style={{padding:20}}><output data-testid="sent">{sent}</output>
 <ActionBar currentRootId="fixture" status="connected" onNewSession={()=>{}} onSelectProject={()=>{}} onSelectSession={()=>{}}
 currentSession={prior === null ? null : {key:"existing", name:"existing", type:"chat", agent:"rcc", model:"opus", effort:prior}}
 onSendMessage={async (_message,_mode,agent,model,_agentMode,effort)=>setSent(JSON.stringify({agent,model,effort}))}/>
 </main></I18nProvider>;
}
createRoot(document.getElementById("root")!).render(<Fixture/>);
