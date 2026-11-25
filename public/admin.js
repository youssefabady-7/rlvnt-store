/* RLVNT admin. All authentication is server-side (httpOnly cookie). No secrets here. Text is always set with textContent. */
const API = (window.RLVNT_API || "") + "/api/admin";
const $ = (id) => document.getElementById(id);
const el = (tag, text, cls, attrs) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; if (attrs) Object.assign(e, attrs); return e; };
const SIZES = ["S", "M", "L", "XL", "XXL"];
const src = (u) => (u.startsWith("/") ? u : "/" + u);
let csrf = "", products = [], settings = {};

function toast(t, bad) { const x = $("toast"); x.textContent = t; x.className = "toast on" + (bad ? " bad" : ""); clearTimeout(toast.t); toast.t = setTimeout(() => x.classList.remove("on"), 2600); }

async function api(path, method = "GET", body) {
  const r = await fetch(API + path, { method, credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: body ? JSON.stringify(body) : undefined });
  let d = {}; try { d = await r.json(); } catch {}
  if (r.status === 401 && path !== "/login") { showLogin("Session expired, please sign in again."); throw new Error("auth"); }
  if (!r.ok) { const m = typeof d.detail === "string" ? d.detail : Array.isArray(d.detail) ? d.detail.map((x) => `${(x.loc || []).slice(-1)[0]}: ${x.msg}`).join("; ") : "Something went wrong"; throw new Error(m); }
  return d;
}
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { if (e.message !== "auth") toast(e.message, true); } };

/* ---------- login ---------- */
function showLogin(msg) { $("app").classList.add("hidden"); $("login").classList.remove("hidden"); $("loginErr").textContent = msg || ""; $("pw").value = ""; csrf = ""; }
async function boot() {
  try {
    const st = await (await fetch(API + "/status", { credentials: "same-origin" })).json();
    if (!st.enabled) { showLogin("Admin is not set up yet."); $("loginBtn").disabled = true; return; }
    const r = await fetch(API + "/me", { credentials: "same-origin" });
    if (r.ok) { csrf = (await r.json()).csrf; await enter(); } else showLogin("");
  } catch { showLogin("Cannot reach the server."); }
}
$("loginForm").onsubmit = async (e) => {
  e.preventDefault(); $("loginBtn").disabled = true; $("loginErr").textContent = "";
  try { const d = await api("/login", "POST", { password: $("pw").value }); csrf = d.csrf; $("pw").value = ""; await enter(); }
  catch (er) { $("loginErr").textContent = er.message; }
  $("loginBtn").disabled = false;
};
$("logout").onclick = guard(async () => { await api("/logout", "POST"); showLogin("Signed out."); });
async function enter() {
  $("login").classList.add("hidden"); $("app").classList.remove("hidden");
  await Promise.all([loadProducts(), loadSettings()]);
}

/* ---------- tabs ---------- */
document.querySelectorAll("#tabs button").forEach((b) => b.onclick = () => {
  document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
  ["products", "orders", "settings", "backup"].forEach((t) => $("t-" + t).classList.toggle("hidden", t !== b.dataset.t));
  if (b.dataset.t === "orders") loadOrders();
});

/* ---------- products ---------- */
const loadProducts = guard(async () => { products = (await api("/products")).products; renderProducts(); });
function badge(t, cls) { return el("span", t, "badge " + (cls || "")); }
function renderProducts() {
  const q = $("psearch").value.trim().toLowerCase(), box = $("plist"); box.replaceChildren();
  products.forEach((p, i) => {
    if (q && !(p.name + " " + p.category + " " + p.id).toLowerCase().includes(q)) return;
    const row = el("div", null, "prow" + (p.hidden ? " off" : ""));
    row.append(el("img", null, null, { src: src(p.image), alt: "" }));
    const mid = el("div"); mid.append(el("div", p.name, "pn"));
    const pm = el("div", null, "pm"); pm.append(el("span", p.id), el("span", p.category));
    const price = el("input", null, null, { type: "number", min: 1, value: p.price, title: "Price (EGP), saved when you leave the field" });
    price.onchange = guard(async () => { await saveProduct(p.id, { ...p, price: Number(price.value) }); toast("Price saved"); });
    pm.append(price, el("span", "EGP"));
    if (p.hidden) pm.append(badge("HIDDEN")); if (p.sold_out) pm.append(badge("SOLD OUT", "so"));
    mid.append(pm);
    const acts = el("div", null, "acts");
    const mk = (t, fn, cls) => { const b = el("button", t, "ghost " + (cls || "")); b.type = "button"; b.onclick = guard(fn); acts.append(b); };
    mk("↑", () => move(i, -1)); mk("↓", () => move(i, 1));
    mk(p.hidden ? "Show" : "Hide", async () => { await saveProduct(p.id, { ...p, hidden: !p.hidden }); });
    mk(p.sold_out ? "In stock" : "Sold out", async () => { await saveProduct(p.id, { ...p, sold_out: !p.sold_out }); });
    mk("Edit", async () => openEditor(p));
    mk("Delete", async () => { if (confirm(`Delete "${p.name}"? You can undo once with "Undo last change".`)) { await api("/products/" + p.id, "DELETE"); toast("Deleted"); await loadProducts(); } }, "danger");
    row.append(mid, acts); box.append(row);
  });
  if (!box.children.length) box.append(el("p", "No products.", "muted"));
}
async function saveProduct(id, p) {
  const body = payload(p); const d = await api("/products/" + id, "PUT", body);
  const i = products.findIndex((x) => x.id === id); products[i] = d.product; renderProducts();
}
const payload = (p) => ({ name: p.name, price: Number(p.price), category: p.category, sizes: p.sizes, description: p.description || "", tags: p.tags || [], image: p.image, images: p.images || [], hidden: !!p.hidden, sold_out: !!p.sold_out });
async function move(i, d) {
  const j = i + d; if (j < 0 || j >= products.length) return;
  [products[i], products[j]] = [products[j], products[i]]; renderProducts();
  try { await api("/products-reorder", "POST", { ids: products.map((p) => p.id) }); } catch (e) { await loadProducts(); throw e; }
}
$("psearch").oninput = renderProducts;
$("undo").onclick = guard(async () => { if (confirm("Undo the last product change?")) { const d = await api("/revert", "POST"); toast(`Restored (${d.count} products)`); await loadProducts(); } });
$("addP").onclick = () => openEditor(null);

/* ---------- editor ---------- */
function openEditor(p) {
  const isNew = !p; const d = p ? JSON.parse(JSON.stringify(p)) : { name: "", price: 800, category: "", sizes: [...SIZES], description: "", tags: [], image: "", images: [], hidden: false, sold_out: false };
  let imgs = d.images && d.images.length ? [...d.images] : d.image ? [d.image] : [];
  const f = $("pform"); f.replaceChildren();
  const field = (label, input) => { const w = el("div", null, "f"); w.append(el("label", label), input); return w; };
  const name = el("input", null, null, { value: d.name, maxLength: 80, required: true });
  const price = el("input", null, null, { type: "number", min: 1, max: 100000, value: d.price, required: true });
  const cat = el("input", null, null, { value: d.category, maxLength: 30, required: true }); cat.setAttribute("list", "cats");
  const dl = el("datalist"); dl.id = "cats"; [...new Set(products.map((x) => x.category))].forEach((c) => dl.append(el("option", null, null, { value: c })));
  const desc = el("textarea", null, null, { value: d.description, maxLength: 600, rows: 3 });
  const tags = el("input", null, null, { value: (d.tags || []).join(", "), placeholder: "comma separated" });
  const r2 = el("div", null, "row2"); r2.append(field("Name", name), field("Price (EGP)", price));
  const sz = el("div", null, "chk"); const szBoxes = SIZES.map((s) => { const l = el("label"); const c = el("input", null, null, { type: "checkbox", checked: d.sizes.includes(s) }); l.append(c, document.createTextNode(s)); sz.append(l); return [s, c]; });
  const flags = el("div", null, "chk"); const mkFlag = (t, v) => { const l = el("label"); const c = el("input", null, null, { type: "checkbox", checked: v }); l.append(c, document.createTextNode(t)); flags.append(l); return c; };
  const hid = mkFlag("Hidden from the store", d.hidden), sold = mkFlag("Sold out", d.sold_out);
  const imgBox = el("div", null, "imgs"), file = el("input", null, null, { type: "file", accept: "image/*", multiple: true });
  const drawImgs = () => {
    imgBox.replaceChildren();
    imgs.forEach((u, i) => {
      const c = el("div", null, "im"); c.append(el("small", i === 0 ? "MAIN" : ""), el("img", null, null, { src: src(u), alt: "" }));
      const mk = (t, fn) => { const b = el("button", t); b.type = "button"; b.onclick = fn; c.append(b); };
      if (i > 0) mk("◀ main", () => { imgs.unshift(imgs.splice(i, 1)[0]); drawImgs(); });
      mk("✕", () => { imgs.splice(i, 1); drawImgs(); });
      imgBox.append(c);
    });
    if (!imgs.length) imgBox.append(el("span", "No images yet", "muted"));
  };
  drawImgs();
  const status = el("p", "", "muted");
  file.onchange = async () => {
    for (const fl of file.files) {
      if (imgs.length >= 8) { status.textContent = "Max 8 images."; break; }
      status.textContent = `Uploading ${fl.name}...`;
      try { const data = await shrink(fl); const r = await api("/image", "POST", { data }); imgs.push(r.url); drawImgs(); status.textContent = ""; }
      catch (e) { status.textContent = "Upload failed: " + e.message; }
    }
    file.value = "";
  };
  const save = el("button", isNew ? "Add product" : "Save changes", "btn"), cancel = el("button", "Cancel", "ghost"); cancel.type = "button";
  cancel.onclick = () => $("modal").classList.add("hidden");
  const actions = el("div", null, "bar"); actions.append(save, cancel);
  f.append(el("h3", isNew ? "Add product" : "Edit " + d.id), r2, field("Category", cat), dl, field("Sizes", sz), field("Description", desc), field("Tags", tags), field("Images (first one is the main image)", imgBox), file, status, flags, actions);
  f.onsubmit = guard(async (e) => {
    e.preventDefault();
    if (!imgs.length) { toast("Add at least one image", true); return; }
    const body = { name: name.value.trim(), price: Number(price.value), category: cat.value.trim().toLowerCase(), sizes: szBoxes.filter(([, c]) => c.checked).map(([s]) => s), description: desc.value, tags: tags.value.split(",").map((t) => t.trim()).filter(Boolean), image: imgs[0], images: imgs.length > 1 ? imgs : [], hidden: hid.checked, sold_out: sold.checked };
    if (!body.sizes.length) { toast("Pick at least one size", true); return; }
    save.disabled = true;
    try { await api(isNew ? "/products" : "/products/" + d.id, isNew ? "POST" : "PUT", body); } finally { save.disabled = false; }
    $("modal").classList.add("hidden"); toast("Saved"); await loadProducts();
  });
  $("modal").classList.remove("hidden"); name.focus();
}
function shrink(fl) { // resize in the browser so uploads stay small (max 1000px, JPEG)
  return new Promise((res, rej) => {
    if (!/^image\//.test(fl.type)) return rej(new Error("not an image"));
    const url = URL.createObjectURL(fl), im = new Image();
    im.onload = () => {
      const k = Math.min(1, 1000 / Math.max(im.width, im.height)), c = document.createElement("canvas");
      c.width = Math.round(im.width * k); c.height = Math.round(im.height * k);
      const x = c.getContext("2d"); x.fillStyle = "#fff"; x.fillRect(0, 0, c.width, c.height); x.drawImage(im, 0, 0, c.width, c.height); URL.revokeObjectURL(url);
      let q = 0.86, out = c.toDataURL("image/jpeg", q);
      while (out.length * 0.75 > 560000 && q > 0.4) { q -= 0.08; out = c.toDataURL("image/jpeg", q); }
      out.length * 0.75 > 560000 ? rej(new Error("image too large")) : res(out.split(",")[1]);
    };
    im.onerror = () => rej(new Error("cannot read image")); im.src = url;
  });
}

/* ---------- orders ---------- */
const loadOrders = guard(async () => {
  const d = await api("/orders"); const box = $("olist"); box.replaceChildren();
  $("oinfo").textContent = `${d.total} order${d.total === 1 ? "" : "s"} saved (kept 90 days)`;
  d.orders.forEach((o) => {
    const c = el("div", null, "o" + (o.status === "done" ? " done" : ""));
    const h = el("div", null, "oh"); h.append(el("b", `${o.order}  ·  ${o.total} EGP`), el("span", new Date((o.ts || 0) * 1000).toLocaleString(), "muted"));
    const b = el("button", o.status === "done" ? "Mark as new" : "Mark as done", "ghost"); b.onclick = guard(async () => { await api("/orders/" + o.order, "PUT", { status: o.status === "done" ? "new" : "done" }); await loadOrders(); });
    h.append(b); c.append(h, el("pre", o.text || "")); box.append(c);
  });
  if (!d.orders.length) box.append(el("p", "No saved orders yet.", "muted"));
});
$("reloadO").onclick = loadOrders;

/* ---------- settings ---------- */
const FIELDS = [
  ["store_name", "Store name", "text"], ["announcement", "Announcement bar text", "text"], ["shipping_fee", "Shipping fee (EGP)", "number"],
  ["delivery_text", "Delivery info (optional, shown to customers and the chatbot)", "textarea", "Example: Delivery takes 2 to 4 days."],
  ["return_text", "Returns info (optional)", "textarea", "Example: Returns accepted within 5 days."],
  ["support_phone", "Support phone", "text"], ["support_email", "Support email", "text"],
  ["whatsapp_number", "WhatsApp number (digits with country code)", "text", "Example: 201270383409"],
  ["order_email", "Order notification email", "text", "Keep this as the email of the Resend account, otherwise order emails may not arrive. Orders are always saved in the order store anyway."],
  ["chatbot_enabled", "Chatbot is on", "checkbox"],
];
const loadSettings = guard(async () => { settings = (await api("/settings")).settings; $("brand").textContent = settings.store_name + " Admin"; renderSettings(); });
function renderSettings() {
  const f = $("sform"); f.replaceChildren(); const inputs = {};
  FIELDS.forEach(([k, label, type, hint]) => {
    const w = el("div", null, "f"); let i;
    if (type === "textarea") i = el("textarea", null, null, { rows: 2, value: settings[k] || "" });
    else if (type === "checkbox") { w.classList.add("cb"); i = el("input", null, null, { type: "checkbox", checked: !!settings[k] }); const l = el("label", null, null); l.style.cssText = "display:flex;gap:8px;align-items:center"; l.append(i, document.createTextNode(label)); w.append(l); }
    else i = el("input", null, null, { type, value: settings[k] ?? "" });
    inputs[k] = i; if (type !== "checkbox") w.append(el("label", label), i); if (hint) w.append(el("span", hint, "hint")); f.append(w);
  });
  const b = el("button", "Save settings", "btn"); f.append(b);
  f.onsubmit = guard(async (e) => {
    e.preventDefault(); const body = {};
    FIELDS.forEach(([k, , type]) => { body[k] = type === "checkbox" ? inputs[k].checked : type === "number" ? Number(inputs[k].value) : inputs[k].value; });
    settings = (await api("/settings", "PUT", body)).settings; toast("Settings saved"); $("brand").textContent = settings.store_name + " Admin";
  });
}

/* ---------- backup ---------- */
$("dl").onclick = guard(async () => {
  const d = await api("/export"); const a = el("a", null, null, { href: URL.createObjectURL(new Blob([JSON.stringify(d, null, 1)], { type: "application/json" })), download: `rlvnt-backup-${new Date().toISOString().slice(0, 10)}.json` });
  document.body.append(a); a.click(); a.remove(); toast("Backup downloaded");
});
$("restore").onclick = guard(async () => {
  const fl = $("restoreFile").files[0]; if (!fl) { toast("Choose a backup file first", true); return; }
  let d; try { d = JSON.parse(await fl.text()); } catch { toast("Not a valid backup file", true); return; }
  if (!confirm(`Replace ALL products (${(d.products || []).length}) and settings with this backup?`)) return;
  const r = await api("/import", "POST", { settings: d.settings, products: d.products }); toast(`Restored ${r.products} products`); await Promise.all([loadProducts(), loadSettings()]);
});

boot();
