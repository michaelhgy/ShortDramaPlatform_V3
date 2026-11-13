// Legacy edit-flow regressions automatically accept custom confirmations.
// Dedicated dialog checks exercise cancel, focus, Escape and close behavior manually.
exports.acceptConfirmations=async page=>page.addInitScript(()=>{
 const attach=()=>{
  new MutationObserver(()=>{const modal=document.getElementById('confirm-modal');if(modal&&!modal.hidden)document.getElementById('confirm-accept').click();}).observe(document.body,{subtree:true,attributes:true,attributeFilter:['hidden']});
 };
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',attach,{once:true});else attach();
});
