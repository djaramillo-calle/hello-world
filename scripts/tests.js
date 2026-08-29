console.log("=== FREQUENCY LIST ===");
console.log("  unique words: "+BANK.k1.length+"   label used in UI: ~"+BANK.k1label);
console.log("  duplicates remaining: "+(BANK.k1.length-new Set(BANK.k1).size));
["the","people","because","quagmire","obdurate","meander"].forEach(w=>
  console.log("    '"+w+"' in core list: "+BANK.k1set.has(w)));
console.log("\n=== VOCAB VALIDITY GATE ===");
function sim(hitRate,f){
  const valid = f<=0.30;
  const corr = f>=1?0:Math.max(0,(hitRate-f)/(1-f));
  return {valid, size: Math.round(corr*8000/100)*100};
}
[[1.00,0.00,"knows everything, disciplined"],
 [1.00,0.90,"marks yes on almost everything"],
 [0.75,0.10,"realistic strong learner"],
 [0.60,0.31,"just over the gate"],
 [0.60,0.29,"just under the gate"]].forEach(function(t){
  const r=sim(t[0],t[1]);
  console.log("  h="+t[0].toFixed(2)+" f="+t[1].toFixed(2)+" -> "+(r.valid?("~"+r.size+" families"):"VOID")+"   ("+t[2]+")");
});
console.log("\n=== C-TEST STILL 20 GAPS EACH ===");
BANK.ctest.forEach((p,i)=>{const g=gapText(p.text,20);console.log("  passage "+(i+1)+": "+g.answers.length+(g.answers.length===20?" ok":" !!!"));});
console.log("\n=== BEYOND-CORE RATIO ON A SAMPLE TRANSCRIPT ===");
const t="um so i think the the main thing is that we we had to rewrite the whole authentication layer because the previous implementation was um fundamentally incompatible with the new infrastructure and nobody had anticipated that";
const toks=t.split(" ").filter(w=>!["um","uh","er"].includes(w));
const beyond=toks.filter(w=>!BANK.k1set.has(w));
console.log("  words: "+toks.length+"  beyond core: "+beyond.length+" ("+Math.round(beyond.length/toks.length*100)+"%)");
console.log("  reached: "+[...new Set(beyond)].join(", "));
console.log("  MTLD: "+mtld(toks).toFixed(1));
