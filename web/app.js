"use strict";
const $ = (id) => document.getElementById(id);
let library = {assets: [], errors: []};
let plan = null;
let busy = false;

function status(message, kind = "") {
  $("status").textContent = message;
  $("status").className = kind;
}
function syncButtons() {
  ["scan", "demo", "plan"].forEach(id => $(id).disabled = busy);
  $("export").disabled = busy || !plan || plan.shots.some(s => s.text_review !== "pass");
}
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed.");
  return result;
}
async function action(message, callback) {
  if (busy) return;
  busy = true; syncButtons(); status(message);
  try { await callback(); }
  catch (error) { status(error.message, "error"); }
  finally { busy = false; syncButtons(); }
}
function resetPlan() {
  plan = null;
  $("timeline").replaceChildren();
  const empty = document.createElement("div");
  empty.className = "empty small"; empty.textContent = "Build a new plan to review your selected shots.";
  $("timeline").append(empty); $("result").replaceChildren(); syncButtons();
}
function drawAssets() {
  const query = $("search").value.trim().toLowerCase();
  const items = library.assets.filter(a => query.split(/\s+/).every(t => a.name.toLowerCase().includes(t)));
  $("count").textContent = library.assets.length;
  const duplicates = library.assets.filter(a => a.duplicate_of).length;
  $("stats").textContent = `${library.assets.length - duplicates} unique clips   /   ${duplicates} exact duplicates   /   ${library.errors.length} unreadable files`;
  $("assets").replaceChildren();
  items.forEach(asset => {
    const element = $("asset-template").content.cloneNode(true);
    const img = element.querySelector("img"); img.src = asset.thumbnails[0]; img.alt = "Preview of " + asset.name;
    element.querySelector("h3").textContent = asset.name;
    element.querySelector(".asset-duration").textContent = asset.duration.toFixed(1) + "s";
    element.querySelector(".asset-meta").textContent = `${asset.width} × ${asset.height} · SHA ${asset.sha256.slice(0, 8)}`;
    const badge = element.querySelector(".badge");
    badge.textContent = asset.duplicate_of ? "Exact duplicate · skipped in plans" : "Ready to plan";
    if (asset.duplicate_of) badge.classList.add("duplicate");
    $("assets").append(element);
  });
  if (!items.length) {
    const empty = document.createElement("div"); empty.className = "empty";
    empty.textContent = library.assets.length ? "No filenames match this search." : "No footage indexed yet.";
    $("assets").append(empty);
  }
}
function drawPlan() {
  $("timeline").replaceChildren();
  plan.shots.forEach((shot, index) => {
    const card = document.createElement("article"); card.className = "shot";
    const title = document.createElement("div"); title.className = "shot-title";
    const name = document.createElement("strong"); name.textContent = `${String(index + 1).padStart(2, "0")} / ${shot.name}`;
    const time = document.createElement("span"); time.textContent = `${shot.start.toFixed(2)}s → ${(shot.start + shot.seconds).toFixed(2)}s · ${shot.seconds.toFixed(1)}s`;
    title.append(name, time); card.append(title);
    const strip = document.createElement("div"); strip.className = "filmstrip";
    shot.thumbnails.forEach((src, i) => {
      const frame = document.createElement("div"); frame.className = "frame";
      const image = document.createElement("img"); image.src = src; image.alt = ["Beginning", "Midpoint", "End"][i] + " of " + shot.name;
      const caption = document.createElement("small"); caption.textContent = ["01 / BEGINNING", "02 / MIDPOINT", "03 / END"][i];
      frame.append(image, caption); strip.append(frame);
    });
    const label = document.createElement("label"); label.className = "approval";
    const checkbox = document.createElement("input"); checkbox.type = "checkbox";
    checkbox.addEventListener("change", () => {shot.text_review = checkbox.checked ? "pass" : "pending"; syncButtons();});
    label.append(checkbox, document.createTextNode("I reviewed this interval for visible text and approved the shot."));
    card.append(strip, label); $("timeline").append(card);
  });
  syncButtons();
}
$("search").addEventListener("input", drawAssets);
$("shots").addEventListener("input", resetPlan);
$("demo").addEventListener("click", () => action("Generating and indexing original synthetic demo clips…", async () => {
  const result = await api("/api/demo", {}); library = result.library; $("folder").value = result.folder;
  resetPlan(); drawAssets(); status("Synthetic demo ready: 3 unique clips and 1 exact duplicate. No real travel footage is included.", "success");
}));
$("scan").addEventListener("click", () => action("Indexing footage and creating previews…", async () => {
  const result = await api("/api/scan", {folder: $("folder").value}); library = result.library;
  resetPlan(); drawAssets(); status(`Indexed ${library.assets.length} clips. ${library.errors.length} files could not be read.`, library.errors.length ? "" : "success");
}));
$("plan").addEventListener("click", () => action("Matching shots and previewing the exact selected intervals…", async () => {
  const shots = JSON.parse($("shots").value);
  plan = await api("/api/plan", {shots}); $("result").replaceChildren(); drawPlan();
  status(`Plan ready: ${plan.shots.length} shots / ${plan.total_seconds.toFixed(1)} seconds. Review each shot before exporting.`, "success");
  $("review").scrollIntoView({behavior: "smooth"});
}));
$("export").addEventListener("click", () => action("Rendering your approved rough cut locally…", async () => {
  const result = await api("/api/render", {plan, approved: true});
  const link = document.createElement("a"); link.href = result.url; link.download = result.path.split(/[\\/]/).pop(); link.textContent = "Download your rough cut ↗";
  const video = document.createElement("video"); video.src = result.url; video.controls = true; video.preload = "metadata";
  $("result").replaceChildren(link, video); status("Export complete. A silent 720 × 1280 rough cut is ready.", "success");
}));
api("/api/state").then(result => {library = result.library; if(library.root) $("folder").value = library.root; drawAssets();}).catch(error => status(error.message, "error"));
