import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { createServer } from "vite";

test("RCC ActionBar selects effort before first turn and preserves resumed choices", async () => {
 const server = await createServer({root:fileURLToPath(new URL("../",import.meta.url)),server:{host:"127.0.0.1",port:0}});
 let browser;
 try {
  await server.listen();
  browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
  for (const prior of [null,"","low"]) {
   const page=await browser.newPage({locale:"zh-CN"});
   page.setDefaultTimeout(10000);
   await page.route("**/api/**", route=>route.fulfill({json:route.request().url().includes("/api/agents")?{agents:[{name:"rcc",protocol:"rcc",installed:true,available:true,last_used:true,default_effort:"high",efforts:["low","medium","high","xhigh","max"],models:["opus","fable"].map(id=>({id,name:`${id}（运行端别名）`}))}],shells:[]}:[]}));
   await page.goto(`${server.resolvedUrls.local[0]}tests/rcc-effort.html${prior===null?"":`?prior=${prior}`}`);
   await page.waitForTimeout(600);
   if(prior===null) {
    await page.locator('[data-onboarding="input-controls"] button').nth(2).click();
    await page.getByRole("button",{name:"opus（运行端别名）",exact:true}).click();
   }
   const send=async (want, wantModel)=>{
    await page.locator('[contenteditable="true"]').fill("test effort");
    await page.locator('[data-onboarding="send-action"]').click();
    await page.waitForFunction(({want,wantModel})=>{try{const sent=JSON.parse(document.querySelector('[data-testid="sent"]').textContent);return wantModel ? sent.model===wantModel : sent.effort===want}catch{return false}},{want,wantModel});
    assert.equal(JSON.parse(await page.getByTestId("sent").textContent()).effort,want);
   };
   await send(prior||"high");
   await page.locator('[data-onboarding="input-controls"] button').nth(2).click();
   await page.getByRole("button").filter({hasText:/^思考等级/}).click();
   await page.getByText("默认 high；选项来自运行端 CLI，当前模型与账号的兼容性由运行端验证。",{exact:true}).waitFor();
   for(const effort of ["low","medium","high","xhigh","max"]) assert.equal(await page.getByRole("button",{name:effort,exact:true}).count(),1);
   await page.getByRole("button",{name:"max",exact:true}).click();
   await send("max");
   await page.locator('[data-onboarding="input-controls"] button').nth(2).click();
   await page.getByRole("button",{name:"fable（运行端别名）",exact:true}).click();
   await send("max", "fable");
   await page.close();
  }
 } finally { await browser?.close();await server.close(); }
});
