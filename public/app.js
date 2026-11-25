const API = window.RLVNT_API;
const $ = (id) => document.getElementById(id);
const el = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };
let cart = JSON.parse(localStorage.getItem("rl_cart") || "{}");
let products = [], filter = "all", query = "", sortBy = "new";
let wish = JSON.parse(localStorage.getItem("rl_wish") || "[]");
const saveWish = () => localStorage.setItem("rl_wish", JSON.stringify(wish));
function toggleWish(id) { wish = wish.includes(id) ? wish.filter((x) => x !== id) : [...wish, id]; saveWish(); renderFilters(); toast(wish.includes(id) ? "Saved" : "Removed from saved"); }
let sizes = JSON.parse(localStorage.getItem("rl_sizes") || "{}");
const SIZES = ["S", "M", "L", "XL", "XXL"], SHIPPING = 100;
let history = JSON.parse(sessionStorage.getItem("rl_chat") || "[]");

/* ---------- helpers ---------- */
function toast(t) { const x = $("toast"); x.textContent = t; x.classList.add("on"); clearTimeout(toast.t); toast.t = setTimeout(() => x.classList.remove("on"), 2200); }
function saveCart(c, opts = {}) {
  const before = Object.values(cart).reduce((a, b) => a + b, 0);
  cart = c; localStorage.setItem("rl_cart", JSON.stringify(cart)); renderCart();
  const after = Object.values(cart).reduce((a, b) => a + b, 0);
  if (after > before) { const b = $("cartBtn"); b.classList.remove("bump"); void b.offsetWidth; b.classList.add("bump"); }
}
function fly(imgEl) {
  if (!imgEl || !imgEl.getBoundingClientRect) return;
  const r = imgEl.getBoundingClientRect(), t = $("cartBtn").getBoundingClientRect();
  const c = imgEl.cloneNode(); Object.assign(c.style, { position: "fixed", left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px", objectFit: "contain", zIndex: 200, pointerEvents: "none", transition: "none" });
  document.body.append(c);
  c.animate([{ transform: "none", opacity: 1 }, { transform: `translate(${t.left - r.left}px,${t.top - r.top}px) scale(.08) rotate(25deg)`, opacity: .2 }],
    { duration: 750, easing: "cubic-bezier(.5,0,.8,.4)" }).onfinish = () => c.remove();
}
function addItem(p, imgEl) { saveCart({ ...cart, [p.id]: Math.min((cart[p.id] || 0) + 1, 20) }); fly(imgEl); toast(`${p.name} added`); }

/* ---------- hero ---------- */
function splitHeadline() {
  const h = $("headline"); const lines = ["WEAR WHAT'S", "RELEVANT"]; h.replaceChildren();
  let i = 0;
  lines.forEach((line, li) => {
    [...line].forEach((ch) => { const s = el("span", ch === " " ? "\u00a0" : ch, "ch" + (li === 1 ? " rl" : "")); s.style.animationDelay = (i++ * 35) + "ms"; h.append(s); });
    if (li === 0) h.append(document.createElement("br"));
  });
}
function renderFloaters() {
  const pick = ["rl-003", "rl-013", "rl-011", "rl-016"].map((id) => products.find((p) => p.id === id)).filter(Boolean);
  const box = $("floaters"); box.replaceChildren();
  pick.forEach((p, i) => { const d = el("div", null, "fl fl" + (i + 1)); const im = document.createElement("img"); im.src = p.image; im.alt = ""; d.append(im); d.dataset.depth = 12 + i * 6; box.append(d); });
}
addEventListener("mousemove", (e) => {
  const x = e.clientX / innerWidth - .5, y = e.clientY / innerHeight - .5;
  document.querySelectorAll(".fl").forEach((f) => { const d = +f.dataset.depth; f.style.translate = `${-x * d * 3}px ${-y * d * 3}px`; });
});

/* ---------- shop ---------- */
function renderFilters() {
  const cats = ["all", ...new Set(products.map((p) => p.category)), "saved"]; const box = $("filters"); box.replaceChildren();
  cats.forEach((c) => { const b = el("button", c === "saved" ? `♥ saved${wish.length ? " (" + wish.length + ")" : ""}` : c, c === filter ? "on" : ""); b.onclick = () => { filter = c; renderFilters(); renderGrid(); }; box.append(b); });
}
function renderGrid() {
  const g = $("grid"); g.replaceChildren();
  let list = products.filter((p) => (filter === "all" || (filter === "saved" ? wish.includes(p.id) : p.category === filter)) && (!query || (p.name + " " + p.category + " " + (p.tags || []).join(" ")).toLowerCase().includes(query)));
  if (sortBy === "az") list = [...list].sort((x, y) => x.name.localeCompare(y.name));
  if (sortBy === "za") list = [...list].sort((x, y) => y.name.localeCompare(x.name));
  $("resCount").textContent = `${list.length} piece${list.length === 1 ? "" : "s"}`;
  if (!list.length) g.append(el("p", filter === "saved" ? "No saved pieces yet. Tap the heart on any piece." : "Nothing matches your search.", "nores"));
  list.forEach((p, i) => {
    const c = el("article", null, "card"); c.style.setProperty("--d", (i % 6) * 90 + "ms");
    const pic = el("div", null, "pic"); const img = document.createElement("img"); img.src = p.image; img.alt = p.name; img.loading = "lazy"; pic.append(img);
    pic.append(el("span", "Quick view", "qvpill"), el("i", null, "shine"));
    const hb = el("button", wish.includes(p.id) ? "♥" : "♡", "heart" + (wish.includes(p.id) ? " on" : "")); hb.setAttribute("aria-label", "Save"); hb.onclick = (ev) => { ev.stopPropagation(); toggleWish(p.id); hb.classList.toggle("on"); hb.textContent = hb.classList.contains("on") ? "♥" : "♡"; if (filter === "saved") renderGrid(); }; pic.append(hb);
    const mv = (e) => { const r = c.getBoundingClientRect(); const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      c.style.setProperty("--mx", x * 100 + "%"); c.style.setProperty("--my", y * 100 + "%");
      img.style.transform = `scale(1.08) rotateY(${(x - .5) * 16}deg) rotateX(${(.5 - y) * 16}deg) translateZ(30px)`; };
    c.addEventListener("mousemove", mv);
    c.addEventListener("mouseleave", () => { img.style.transform = ""; });
    pic.onclick = () => openQV(p);
    const meta = el("div", null, "meta");
    const top = el("div", null, "mtop"); top.append(el("span", String(i + 1).padStart(2, "0"), "idx"), el("span", p.category, "cat"));
    meta.append(top, el("h4", p.name));
    const row = el("div", null, "mrow"); row.append(el("span", `${p.price} EGP`, "pr"));
    const add = el("button", "Add +", "add"); add.onclick = (ev) => { ev.stopPropagation(); addItem(p, img); add.classList.add("ok"); setTimeout(() => add.classList.remove("ok"), 900); };
    row.append(add); meta.append(row);
    c.append(pic, meta); g.append(c); io.observe(c);
  });
}
/* quick view */
function openQV(p) {
  const q = $("qv"); const box = $("qvBody"); box.replaceChildren();
  const left = el("div", null, "qvimg"); const im = document.createElement("img"); im.src = p.image; im.alt = p.name; left.append(im);
  left.addEventListener("mousemove", (e) => { const r = left.getBoundingClientRect(); im.style.transformOrigin = `${(e.clientX - r.left) / r.width * 100}% ${(e.clientY - r.top) / r.height * 100}%`; im.style.transform = "scale(1.9)"; });
  left.addEventListener("mouseleave", () => { im.style.transform = ""; });
  const right = el("div", null, "qvinfo");
  right.append(el("span", p.category, "cat"), el("h3", p.name), el("p", `${p.price} EGP`, "pr"), el("p", p.description, "desc"));
  const sz = el("div", null, "pills"); let chosen = sizes[p.id] || "";
  SIZES.forEach((s) => { const b = el("button", s, "pill" + (s === chosen ? " on" : "")); b.type = "button"; b.onclick = () => { chosen = s; sizes[p.id] = s; localStorage.setItem("rl_sizes", JSON.stringify(sizes)); sz.querySelectorAll(".pill").forEach((x) => x.classList.toggle("on", x.textContent === s)); }; sz.append(b); });
  const add = el("button", "Add to cart", "btn full"); add.onclick = () => { addItem(p, im); renderCart(); setTimeout(() => closeQV(), 350); };
  const sg = el("button", "Size guide", "linkbtn"); sg.type = "button"; sg.onclick = () => right.querySelector(".guide").classList.toggle("open");
  const guide = el("div", null, "guide"); guide.innerHTML = '<table><tr><th>Size</th><th>Length</th><th>Chest</th><th>Sleeve</th></tr><tr><td>S</td><td>72</td><td>58</td><td>63.6</td></tr><tr><td>M</td><td>74</td><td>61</td><td>64</td></tr><tr><td>L</td><td>76</td><td>64</td><td>64.4</td></tr><tr><td>XL</td><td>78</td><td>67</td><td>64.8</td></tr><tr><td>XXL</td><td>79</td><td>70</td><td>65.2</td></tr></table><small>Approximate, in cm, oversized fit. Ask the assistant if unsure.</small>';
  const rel = el("div", null, "related"); rel.append(el("small", "You may also like"));
  const rr = el("div", null, "rrow"); products.filter((x) => x.id !== p.id && x.category === p.category).slice(0, 4).concat(products.filter((x) => x.category !== p.category)).slice(0, 4).forEach((x) => { const t = el("button", null, "rthumb"); t.type = "button"; const ti = document.createElement("img"); ti.src = x.image; ti.alt = x.name; ti.title = x.name; t.append(ti); t.onclick = () => openQV(x); rr.append(t); }); rel.append(rr);
  const wa = el("a", "Order via WhatsApp", "linkbtn"); wa.target = "_blank"; wa.rel = "noopener"; wa.href = "https://wa.me/201270383409?text=" + encodeURIComponent(`Hi RLVNT, I want the ${p.name} (${p.id}), size ${sizes[p.id] || "?"}`);
  right.append(el("small", "Size (all available)"), sz, sg, guide, add, wa, rel, el("p", "Cash on delivery · 3 to 5 days · 100 EGP shipping", "note"));
  box.append(left, right); q.classList.add("on"); document.body.style.overflow = "hidden";
}
function closeQV() { $("qv").classList.remove("on"); document.body.style.overflow = ""; }
$("qvClose").onclick = closeQV; $("qv").addEventListener("click", (e) => { if (e.target.id === "qv") closeQV(); });
addEventListener("keydown", (e) => { if (e.key === "Escape") { closeQV(); openCart(false); } });
const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: .12 });
document.querySelectorAll(".reveal").forEach((n) => io.observe(n));

/* ---------- cart ---------- */
function renderCart() {
  const box = $("cartItems"); box.replaceChildren(); let total = 0, count = 0;
  for (const [id, q] of Object.entries(cart)) {
    const p = products.find((x) => x.id === id); if (!p) continue; total += q * p.price; count += q;
    const row = el("div", null, "line"); const im = document.createElement("img"); im.src = p.image; im.alt = p.name;
    const info = el("div"); info.append(el("b", p.name), el("small", `${p.price} EGP`));
    const qty = el("div", null, "qty"); const m = el("button", "−"), pl = el("button", "+");
    m.onclick = () => { const c = { ...cart }; if (c[id] > 1) c[id]--; else delete c[id]; saveCart(c); };
    pl.onclick = () => saveCart({ ...cart, [id]: Math.min(q + 1, 20) });
    qty.append(m, el("span", String(q)), pl); info.append(qty);
    const sz = el("div", null, "sz"); const sel = document.createElement("select"); sel.dataset.id = id;
    const ph = el("option", "Size"); ph.value = ""; sel.append(ph); SIZES.forEach((s) => { const o = el("option", s); o.value = s; sel.append(o); });
    sel.value = sizes[id] || ""; sel.onchange = () => { sizes[id] = sel.value; localStorage.setItem("rl_sizes", JSON.stringify(sizes)); sel.classList.remove("bad"); };
    sz.append(sel); info.append(sz);
    row.append(im, info, el("b", `${q * p.price}`)); box.append(row);
  }
  if (!count) box.append(el("p", "Your cart is empty.", "empty"));
  const ship = count ? SHIPPING : 0;
  $("sub").textContent = total; $("ship").textContent = ship; $("total").textContent = total + ship; $("total2").textContent = total + ship; $("count").textContent = count;
  $("checkoutBtn").disabled = !count;
}
const mode = (m) => { const d = $("cart"); d.classList.remove("mode-form", "mode-done"); if (m) d.classList.add("mode-" + m); $("orderForm").classList.toggle("hidden", m !== "form"); $("orderDone").classList.toggle("hidden", m !== "done"); };
$("checkoutBtn").onclick = () => {
  const missing = [...document.querySelectorAll("#cartItems select")].filter((s) => !s.value);
  if (missing.length) { missing.forEach((s) => s.classList.add("bad")); toast("Choose a size for each piece"); return; }
  $("orderErr").textContent = ""; mode("form");
};
$("backCart").onclick = () => mode(null);
$("orderForm").onsubmit = async (e) => {
  e.preventDefault(); const f = e.target; const btn = $("submitOrder"); $("orderErr").textContent = "";
  const v = (n) => f.elements[n].value.trim();
  if (v("name").length < 2 || v("city").length < 2 || v("address").length < 5 || !/^\+?[0-9 ()-]{8,20}$/.test(v("phone"))) { $("orderErr").textContent = "Please fill name, a valid phone, city and address."; return; }
  const items = Object.entries(cart).map(([id, qty]) => ({ id, size: sizes[id], qty }));
  btn.disabled = true;
  try {
    const r = await fetch(API + "/api/order", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: v("name"), phone: v("phone"), city: v("city"), address: v("address"), notes: v("notes"), website: v("website"), items }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { $("orderErr").textContent = typeof d.detail === "string" ? d.detail : "Please check your details and try again."; btn.disabled = false; return; }
    const box = $("orderDone"); box.replaceChildren(el("div", "✓", "check"), el("h3", "Order placed"), el("p", `Order ${d.order_number}`), el("p", `Pay ${d.total} EGP cash on delivery. Delivery in 3 to 5 days. We may confirm by phone or WhatsApp.`),
      el("p", "Questions? youssefabady6@gmail.com · +201270383409"));
    const ok = el("button", "Continue shopping", "btn full"); ok.onclick = () => { mode(null); openCart(false); }; box.append(ok);
    saveCart({}); sizes = {}; localStorage.removeItem("rl_sizes"); f.reset(); mode("done");
  } catch { $("orderErr").textContent = "Connection problem. Please try again."; }
  btn.disabled = false;
};
const openCart = (on) => { $("cart").classList.toggle("on", on); $("scrim").classList.toggle("on", on); };
$("cartBtn").onclick = () => { if ($("cart").classList.contains("mode-done")) mode(null); openCart(true); }; $("closeCart").onclick = () => openCart(false); $("scrim").onclick = () => openCart(false);

/* ---------- chat ---------- */
const CHIPS = ["Show me hoodies", "What sizes do you have?", "What's your return policy?", "عايز حاجة من ريال مدريد", "الشحن بكام وبيوصل امتى؟"];
function rich(text, parent) { text.split(/(\*\*[^*]+\*\*)/g).forEach((s) => { if (s.startsWith("**") && s.endsWith("**")) parent.append(el("strong", s.slice(2, -2))); else parent.append(document.createTextNode(s)); }); }
function bubble(role, text) { const m = el("div", null, "msg " + (role === "user" ? "me" : "bot")); m.dir = "auto"; rich(text, m); $("log").append(m); scroll(); return m; }
function scroll() { const l = $("log"); l.scrollTop = l.scrollHeight; }
function productCards(list) {
  if (!list || !list.length) return; const w = el("div", null, "pcards");
  list.slice(0, 5).forEach((p) => { const c = el("div", null, "pc"); const im = document.createElement("img"); im.src = p.image; im.alt = p.name; const d = el("div", p.name); const b = el("button", "Add"); b.onclick = () => addItem(p, im); c.append(im, d, b); w.append(c); });
  $("log").append(w); scroll();
}
function openChat(on = true) { $("chat").classList.toggle("on", on); $("chatFab").style.display = on ? "none" : ""; if (on) $("input").focus(); }
$("chatFab").onclick = () => openChat(true); $("chatClose").onclick = () => openChat(false);
$("askBtn").onclick = () => openChat(true);
function renderChips() { const b = $("chips"); b.replaceChildren(); CHIPS.forEach((t) => { const x = el("button", t); x.dir = "auto"; x.onclick = () => send(t); b.append(x); }); }
async function send(text) {
  text = (text || "").trim(); if (!text) return; $("chips").replaceChildren();
  bubble("user", text); history.push({ role: "user", content: text }); $("input").value = "";
  const t = el("div", null, "msg bot typing"); t.append(el("i"), el("i"), el("i")); $("log").append(t); scroll();
  try {
    const r = await fetch(API + "/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: history.slice(-14), cart }) });
    const d = await r.json().catch(() => ({})); t.remove();
    if (!r.ok) { bubble("assistant", d.detail || "Something went wrong. حاول تاني بعد شوية."); history.pop(); return; }
    bubble("assistant", d.reply || "…"); history.push({ role: "assistant", content: d.reply || "" });
    productCards(d.products); saveCart(d.cart);
  } catch { t.remove(); bubble("assistant", "Connection problem. Please try again. في مشكلة في الاتصال، حاول تاني."); history.pop(); }
  sessionStorage.setItem("rl_chat", JSON.stringify(history.slice(-30)));
}
$("form").onsubmit = (e) => { e.preventDefault(); send($("input").value); };
function restoreChat() {
  if (history.length) history.forEach((m) => bubble(m.role, m.content));
  else { bubble("assistant", "Hey, I'm the RLVNT assistant. Ask about pieces, sizing, shipping, returns or tell me what to add to your cart.\nأهلاً! اسألني عن أي قطعة أو الشحن أو الاسترجاع، أو قولي أضيف إيه للسلة."); renderChips(); }
}

/* ---------- page chrome ---------- */
addEventListener("scroll", () => {
  $("nav").classList.toggle("solid", scrollY > 40);
  $("progress").style.width = (scrollY / (document.documentElement.scrollHeight - innerHeight) * 100) + "%";
}, { passive: true });

splitHeadline(); restoreChat();
fetch(API + "/api/products").then((r) => r.json()).then((d) => { products = d.products; renderFloaters(); renderFilters(); renderGrid(); renderCart(); })
  .catch(() => toast("Could not load products. Please refresh."));

$("q").oninput = (e) => { query = e.target.value.trim().toLowerCase(); renderGrid(); };
$("sort").onchange = (e) => { sortBy = e.target.value; renderGrid(); };
(function skel() { const g = $("grid"); for (let i = 0; i < 6; i++) g.append(el("div", null, "skel")); })();
addEventListener("scroll", () => { $("nav").classList.toggle("stuck", scrollY > 30); $("toTop").classList.toggle("on", scrollY > 900); }, { passive: true });
$("toTop").onclick = () => scrollTo({ top: 0, behavior: "smooth" });
