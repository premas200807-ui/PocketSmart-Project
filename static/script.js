/* ===== PocketSmart AI - shared frontend helpers (script.js) ===== */

const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function titleCase(s) {
  return String(s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function showAlert(el, msg, type = "error") {
  if (!el) return;
  el.className = `alert alert-${type} show`;
  el.textContent = msg;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
}

function hideAlert(el) { if (el) el.className = "alert"; }

/** fetch wrapper: handles 401 (session expired) and FastAPI error messages */
async function api(url, options = {}) {
  const res = await fetch(url, { credentials: "same-origin", ...options });
  let data = null;
  try { data = await res.json(); } catch (e) { /* not json */ }
  if (res.status === 401 && !url.includes("/token")) {
    window.location.href = "/login";
    throw new Error("Session expired. Please log in again.");
  }
  if (!res.ok) {
    let msg = "Something went wrong. Please try again.";
    if (data && data.detail) {
      msg = Array.isArray(data.detail)
        ? data.detail.map((d) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join(", ")
        : data.detail;
    }
    throw new Error(msg);
  }
  return data;
}

const ICONS = {
  lighting: "fa-lightbulb", ceiling_fans: "fa-fan", fans: "fa-fan", furniture: "fa-couch",
  dining_tables: "fa-utensils", decor: "fa-palette", venue: "fa-building", catering: "fa-bowl-food",
  food: "fa-pizza-slice", drinks: "fa-martini-glass", decoration: "fa-wand-magic-sparkles",
  entertainment: "fa-music", photography: "fa-camera", return_gifts: "fa-gift", gifts: "fa-gift",
  contingency: "fa-shield-halved", home: "fa-house", party: "fa-champagne-glasses", jewelry: "fa-gem",
};
const iconFor = (k) => ICONS[String(k || "").toLowerCase().replace(/ /g, "_")] || "fa-tag";

function linksHtml(links) {
  if (!links) return "";
  return `<div class="links">${Object.entries(links)
    .map(([p, url]) => `<a href="${esc(url)}" target="_blank" rel="noopener"><i class="fa-solid fa-cart-shopping"></i> ${esc(p)}</a>`)
    .join("")}</div>`;
}

function listHtml(items) {
  if (!items || !items.length) return "";
  return `<ul class="tips">${items.map((t) => `<li>${esc(typeof t === "string" ? t : JSON.stringify(t))}</li>`).join("")}</ul>`;
}

function summaryHtml(r, title = "Budget Summary") {
  const remainingCls = (r.remaining_budget ?? 0) >= 0 ? "good" : "bad";
  const src = r.source === "gemini"
    ? `<span class="badge badge-ai"><i class="fa-solid fa-robot"></i> Gemini AI</span>`
    : `<span class="badge badge-fallback"><i class="fa-solid fa-circle-info"></i> Default plan</span>`;
  return `
  <div class="result-block">
    <div class="rb-head dark"><h3><i class="fa-solid fa-chart-pie"></i> ${title} &nbsp;${src}</h3></div>
    <div class="rb-body">
      ${r.note ? `<div class="alert alert-info show">${esc(r.note)}</div>` : ""}
      ${r.within_budget === false ? `<div class="alert alert-error show">This plan goes over your budget - consider reducing quantities.</div>` : ""}
      <div class="summary-grid">
        <div class="stat"><span>Total Budget</span><strong>${inr(r.total_budget)}</strong></div>
        <div class="stat"><span>Estimated Spend</span><strong>${inr(r.total_spent)}</strong></div>
        <div class="stat"><span>Remaining Budget</span><strong class="${remainingCls}">${inr(r.remaining_budget)}</strong></div>
      </div>
    </div>
  </div>`;
}

function calcTableHtml(table) {
  if (!table || !table.length) return "";
  return `
  <div class="result-block">
    <div class="rb-head"><h3><i class="fa-solid fa-table"></i> Budget Allocation Table (INR)</h3></div>
    <div class="rb-body table-wrap"><table>
      <tr><th>Category</th><th>Items</th><th>Total Cost</th><th>% of Budget</th><th></th></tr>
      ${table.map((c) => `<tr>
        <td><i class="fa-solid ${iconFor(c.category)}"></i> ${esc(titleCase(c.category))}</td>
        <td>${c.items_count}</td><td>${inr(c.total_cost)}</td><td>${c.percentage_of_budget}%</td>
        <td><div class="bar"><span style="width:${Math.min(100, c.percentage_of_budget)}%"></span></div></td></tr>`).join("")}
    </table></div>
  </div>`;
}

function breakdownHtml(breakdown) {
  return (breakdown || []).map((cat) => `
  <div class="result-block">
    <div class="rb-head">
      <h3><i class="fa-solid ${iconFor(cat.category)}"></i> ${esc(titleCase(cat.category))}</h3>
      <small>Allocation: ${inr(cat.allocation)}</small>
    </div>
    <div class="rb-body table-wrap"><table>
      <tr><th>Item</th><th>Description</th><th>Unit Price</th><th>Qty</th><th>Total</th><th>Shop</th></tr>
      ${(cat.items || []).map((it) => `<tr>
        <td><strong>${esc(it.name)}</strong>${it.brand ? `<br><small>${esc(it.brand)}</small>` : ""}</td>
        <td>${esc(it.description)}</td>
        <td>${inr(it.estimated_price)}</td><td>${it.quantity}</td><td><strong>${inr(it.line_total)}</strong></td>
        <td>${linksHtml(it.shopping_links)}</td></tr>`).join("")}
    </table></div>
  </div>`).join("");
}

function renderHome(r) {
  return `<h2 class="results-title">Your Personalized Home Budget Plan</h2>
    ${summaryHtml(r)}${calcTableHtml(r.calculation_table)}${breakdownHtml(r.budget_breakdown)}
    ${r.additional_suggestions?.length ? `<div class="result-block"><div class="rb-head dark"><h3><i class="fa-solid fa-lightbulb"></i> Additional Suggestions</h3></div><div class="rb-body">${listHtml(r.additional_suggestions)}</div></div>` : ""}`;
}

function renderParty(r) {
  const venues = (r.venue_suggestions || []).length ? `
    <div class="result-block">
      <div class="rb-head"><h3><i class="fa-solid fa-location-dot"></i> Venue Suggestions</h3></div>
      <div class="rb-body table-wrap"><table>
        <tr><th>Venue</th><th>Type</th><th>Capacity</th><th>Est. Cost</th><th>Search</th></tr>
        ${r.venue_suggestions.map((v) => `<tr><td><strong>${esc(v.name)}</strong></td><td>${esc(v.type)}</td>
          <td>${esc(v.capacity)}</td><td>${inr(v.estimated_cost)}</td><td>${linksHtml(v.search_links)}</td></tr>`).join("")}
      </table></div></div>` : "";
  return `<h2 class="results-title">Your Party Budget Plan</h2>
    ${summaryHtml(r)}${calcTableHtml(r.calculation_table_inr || r.calculation_table)}${breakdownHtml(r.budget_breakdown)}${venues}
    ${r.additional_suggestions?.length ? `<div class="result-block"><div class="rb-head dark"><h3><i class="fa-solid fa-lightbulb"></i> Planning Tips</h3></div><div class="rb-body">${listHtml(r.additional_suggestions)}</div></div>` : ""}`;
}

function renderJewelry(r) {
  const oa = r.outfit_analysis;
  const outfit = oa ? `
    <div class="result-block">
      <div class="rb-head"><h3><i class="fa-solid fa-shirt"></i> Outfit Analysis</h3></div>
      <div class="rb-body" style="display:flex;gap:20px;flex-wrap:wrap;align-items:center">
        ${r.outfit_image ? `<img src="${esc(r.outfit_image)}" alt="Outfit" style="max-width:160px;border-radius:10px">` : ""}
        <div>
          <p><strong>Colours:</strong> ${(oa.colors || []).map((c) => `<span class="chip"><span class="color-dot" style="background:${esc(c)}"></span>${esc(c)}</span>`).join(" ")}</p>
          <p><strong>Style:</strong> ${esc(oa.style)}</p>
          <p><strong>Formality:</strong> ${esc(oa.formality)}</p>
        </div>
      </div></div>` : "";
  const recs = `
    <div class="result-block">
      <div class="rb-head"><h3><i class="fa-solid fa-gem"></i> Jewelry Recommendations</h3></div>
      <div class="rb-body table-wrap"><table>
        <tr><th>Item</th><th>Description</th><th>Style</th><th>Price</th><th>Shop</th></tr>
        ${(r.jewelry_recommendations || []).map((j) => `<tr>
          <td><strong>${esc(j.item_type)}</strong>${j.material ? `<br><small>${esc(j.material)}</small>` : ""}</td>
          <td>${esc(j.description)}</td><td>${esc(j.style)}</td><td><strong>${inr(j.estimated_price)}</strong></td>
          <td>${linksHtml(j.shopping_links)}</td></tr>`).join("")}
      </table></div></div>`;
  return `<h2 class="results-title">Your Jewelry Recommendations</h2>
    ${summaryHtml(r)}${outfit}${recs}
    ${r.styling_tips?.length ? `<div class="result-block"><div class="rb-head dark"><h3><i class="fa-solid fa-wand-magic-sparkles"></i> Styling Tips</h3></div><div class="rb-body">${listHtml(r.styling_tips)}</div></div>` : ""}`;
}

function renderResult(type, r) {
  if (type === "home") return renderHome(r);
  if (type === "party") return renderParty(r);
  return renderJewelry(r);
}

/** Shared submit flow for planner pages */
async function runPlanner({ form, button, loader, results, alertEl, type, request }) {
  hideAlert(alertEl);
  results.innerHTML = "";
  button.disabled = true;
  const original = button.innerHTML;
  button.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Generating...`;
  loader.classList.add("show");
  try {
    const data = await request();
    results.innerHTML = renderResult(type, data);
    results.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    showAlert(alertEl, err.message);
  } finally {
    button.disabled = false;
    button.innerHTML = original;
    loader.classList.remove("show");
  }
}

function fmtDate(iso) {
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
}

function historyTitle(h) {
  const i = h.input || {};
  if (h.type === "home") return "Home Interior Budget";
  if (h.type === "party") return `${titleCase(i.party_type || "Party")} Budget Plan`;
  return "Jewelry Budget Plan";
}

function historySubtitle(h) {
  const i = h.input || {};
  let s = `Budget: ${inr(i.total_budget)}`;
  if (h.type === "party") s += ` for ${i.num_guests} guests`;
  if (h.type === "jewelry") s += ` for ${esc(i.occasion)}`;
  return `${s} - ${fmtDate(h.timestamp)}`;
}
