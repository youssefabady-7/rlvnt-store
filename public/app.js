const API = window.RLVNT_API;
let cart = JSON.parse(localStorage.getItem("cart") || "{}");
let products = [], history = [];
const $ = (id) => document.getElementById(id);
const el = (tag, text, cls) => { const e = document.createElement(tag); e.textContent = text; if (cls) e.className = cls; return e; };

function saveCart(c) { cart = c; localStorage.setItem("cart", JSON.stringify(cart)); renderCart(); }

function renderCart() {
  const box = $("cartItems"); box.replaceChildren();
  let total = 0, count = 0;
  for (const [id, q] of Object.entries(cart)) {
    const p = products.find((x) => x.id === id); if (!p) continue;
    total += q * p.price; count += q;
    const row = el("div", "", "row");
    row.append(el("span", `${p.name} x${q}`));
    const b = el("button", "Remove");
    b.onclick = () => { const c = { ...cart }; if (c[id] > 1) c[id]--; else delete c[id]; saveCart(c); };
    row.append(b); box.append(row);
  }
  $("total").textContent = total; $("count").textContent = count;
}

function renderGrid() {
  const g = $("grid"); g.replaceChildren();
  for (const p of products) {
    const c = el("div", "", "card");
    const img = document.createElement("img"); img.src = p.image; img.alt = p.name;
    const b = el("button", "Add to cart");
    b.onclick = () => saveCart({ ...cart, [p.id]: (cart[p.id] || 0) + 1 });
    c.append(img, el("h4", p.name), el("p", `${p.price} EGP`), b); g.append(c);
  }
}

function log(text, cls) { const m = el("div", text, "m " + cls); $("log").append(m); $("log").scrollTop = 1e9; }

$("cartBtn").onclick = () => $("cart").classList.toggle("hidden");
$("form").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("input").value.trim(); if (!text) return;
  $("input").value = ""; log(text, "u"); history.push({ role: "user", content: text });
  try {
    const r = await fetch(API + "/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history, cart }) });
    if (!r.ok) throw new Error((await r.json()).detail || r.status);
    const d = await r.json();
    history.push({ role: "assistant", content: d.reply }); log(d.reply, "a"); saveCart(d.cart);
  } catch (err) { log("Something went wrong: " + err.message, "a"); }
};

fetch(API + "/api/products").then((r) => r.json()).then((d) => { products = d.products; renderGrid(); renderCart(); })
  .catch(() => log("Could not reach the server.", "a"));
log("Hi! Ask me for recommendations or tell me what to add to your cart.", "a");
