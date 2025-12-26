(async () => {
  const $ = (id)=>document.getElementById(id);
  const urls = {
    missing: "../data/gallery_missing.json",
    plan:    "../data/plan_snapshot.json",
    queue:   "../data/queue_snapshot.json"
  };

  async function j(url){
    const r = await fetch(url, {cache:"no-store"});
    if(!r.ok) throw new Error(url + " HTTP " + r.status);
    return r.json();
  }

  function shortList(items, pickFn, max=30){
    const out = [];
    for(const it of items.slice(0,max)) out.push(pickFn(it));
    if(items.length>max) out.push( + more);
    return out.join("\n");
  }

  async function load(){
    // missing
    try{
      const miss = await j(urls.missing);
      missingCounts.textContent = items: ;
      missingList.textContent = shortList(miss, x => ${x.productId}      );
    }catch(e){
      missingCounts.textContent = "missing data not available";
      missingList.textContent = e.message;
    }

    // plan snapshot (object w/ items)
    try{
      const plan = await j(urls.plan);
      const items = Array.isArray(plan.items) ? plan.items : [];
      planCounts.textContent = items: ;
      planList.textContent = shortList(items, x => ${x.productId}  need: );
    }catch(e){
      planCounts.textContent = "plan snapshot not available";
      planList.textContent = e.message;
    }

    // queue snapshot (array)
    try{
      const q = await j(urls.queue);
      const arr = Array.isArray(q) ? q : (Array.isArray(q.items)? q.items : []);
      const pending = arr.filter(x=>x.status==="pending").length;
      const running = arr.filter(x=>x.status==="running").length;
      const done    = arr.filter(x=>x.status==="done").length;
      queueCounts.textContent = 	otal:   pending:   running:   done: ;
      queueList.textContent = shortList(arr, x => ${x.id}      );
    }catch(e){
      queueCounts.textContent = "queue snapshot not available";
      queueList.textContent = e.message;
    }

    cmds.textContent =
# Refresh snapshots (Phase 24 re-run)
cd C:\\EnTrusCore\\scripts
.\\entrus_phase24_creator_panel.ps1

# Detect missing + build plan (Phase 23)
.\\entrus_phase23_missing_detect_and_plan.ps1

# Run one render job safely (Phase 17)
.\\entrus_phase17_comfy_single_job_runner.ps1

# Run safe batch (Phase 18)
.\\entrus_phase18_safe_batch_runner.ps1 -MaxJobs 10

# Resync + rebuild gallery JSON (Phase 19)
.\\entrus_phase19_resync_and_gallery_build.ps1

# Copy finals -> web assets (Phase 20)
.\\entrus_phase20_web_asset_sync_copyonly.ps1

# Local server (Phase 22)
.\\entrus_phase22_local_server.ps1
;
  }

  reload.addEventListener("click", load);
  load();
})();
