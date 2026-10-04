/* DN Product Studio UI - plain JS on top of the local API (server.py). */
"use strict";

const THEMES = {
  gold:     { label: "Gold",     light: ["34 88% 36%", "24 85% 42%", "34 88% 42%", "42 85% 38%"], dark: ["40 92% 58%", "24 85% 40%", "34 88% 42%", "42 85% 38%"], hue: 38 },
  ocean:    { label: "Ocean",    light: ["215 90% 50%", "200 90% 45%", "215 85% 52%", "230 80% 58%"], dark: ["215 95% 65%", "200 95% 35%", "215 90% 40%", "230 85% 45%"], hue: 215 },
  midnight: { label: "Midnight", light: ["262 83% 58%", "240 60% 50%", "280 70% 55%", "320 65% 50%"], dark: ["270 85% 72%", "240 70% 35%", "280 80% 40%", "320 75% 35%"], hue: 268 },
  aurora:   { label: "Aurora",   light: ["175 85% 28%", "160 80% 34%", "190 85% 38%", "220 80% 50%"], dark: ["175 85% 50%", "160 90% 30%", "190 95% 35%", "220 90% 40%"], hue: 180 },
  sunset:   { label: "Sunset",   light: ["22 92% 42%", "15 90% 48%", "28 92% 46%", "40 90% 42%"], dark: ["30 95% 58%", "15 85% 40%", "35 90% 42%", "45 85% 38%"], hue: 28 },
  forest:   { label: "Forest",   light: ["152 75% 28%", "140 70% 32%", "160 65% 34%", "175 60% 34%"], dark: ["152 75% 50%", "140 75% 28%", "160 70% 32%", "175 65% 30%"], hue: 152 },
  candy:    { label: "Candy",    light: ["335 80% 48%", "325 80% 52%", "338 78% 55%", "318 75% 50%"], dark: ["335 90% 68%", "325 85% 42%", "338 85% 48%", "318 80% 44%"], hue: 335 },
};
const CATEGORIES = ["Apparel", "Wall Art", "Mugs", "Gifts", "Books"];
const WEB_STATUS = { "": ["muted", "circle-dashed", "Chưa đăng"], draft: ["info", "file-pen-line", "Bản nháp trên web"], published: ["ok", "globe", "Đang bán trên web"] };

const S = { page: "ebook", app: {}, config: {}, hasToken: false, ebooks: [], pods: [], busy: {}, errors: {},
  notes: null, podErrors: [], update: null, upd: null, ping: null, running: false };
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (name, cls = "") => `<i data-lucide="${name}" class="${cls}"></i>`;
const money = (v) => Number(v || 0).toFixed(2);
const list = (kind) => (kind === "ebook" ? S.ebooks : S.pods);
const find = (kind, id) => list(kind).find((i) => i.id === id);

async function api(path, body = {}) {
  let res;
  try {
    res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Session": window.SESSION_KEY }, body: JSON.stringify(body) });
  } catch (e) {
    throw new Error("Tool đã bị đóng hoặc mất kết nối nội bộ. Hãy mở lại tool.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const err = new Error(data.error || `Lỗi ${res.status}`); err.code = data.code; throw err; }
  return data;
}
function setState(d) {
  if (d.app) S.app = d.app;
  if (d.config) S.config = d.config;
  if ("has_token" in d) S.hasToken = d.has_token;
  if (d.ebooks) S.ebooks = d.ebooks;
  if (d.pods) S.pods = d.pods;
}
function toast(type, text) {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `${icon({ success: "circle-check", error: "circle-alert", info: "info" }[type])}<span>${esc(text)}</span>`;
  $("#toasts").append(el);
  lucide.createIcons();
  setTimeout(() => el.remove(), type === "error" ? 9000 : 4000);
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) { /* fall through */ }
  const ta = document.createElement("textarea");
  ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.append(ta); ta.select();
  const ok = document.execCommand("copy");
  ta.remove();
  return ok;
}

/* ---------------- theme ---------------- */
function applyTheme() {
  const t = THEMES[S.config.theme] || THEMES.gold;
  const dark = S.config.mode !== "light";
  const [primary, from, via, to] = dark ? t.dark : t.light;
  const set = (k, v) => document.documentElement.style.setProperty(k, v);
  document.documentElement.classList.toggle("dark", dark);
  set("--primary", primary); set("--ring", primary);
  set("--gradient-from", from); set("--gradient-via", via); set("--gradient-to", to);
  set("--accent", dark ? `${t.hue} 45% 18%` : `${t.hue} 80% 94%`);
  set("--accent-foreground", dark ? `${t.hue} 90% 84%` : `${t.hue} 85% 26%`);
}

/* ---------------- sidebar ---------------- */
const NAV = [["ebook", "book-open", "Ebook"], ["pod", "shirt", "POD (Spring)"]];
const NAV_BOTTOM = [["guide", "circle-help", "Hướng dẫn"], ["settings", "settings", "Cài đặt"]];
function renderSidebar() {
  const open = S.config.sidebar_open !== false;
  const item = ([id, ic, label]) => `<button class="nav-item ${S.page === id ? "active" : ""}" data-nav="${id}" title="${label}">
    ${icon(ic)}<span class="nav-label">${label}</span>${id === "settings" && S.update?.newer ? '<span class="dot" title="Có bản mới"></span>' : ""}</button>`;
  const dark = S.config.mode !== "light";
  $("#sidebar").className = `sidebar glass-panel ${open ? "" : "closed"}`;
  $("#sidebar").innerHTML = `
    <div class="brand"><div class="brand-mark">${icon("package-plus")}</div><div class="brand-name gradient-text">DN Studio</div></div>
    <nav class="nav">${NAV.map(item).join("")}</nav>
    <nav class="nav bottom">${NAV_BOTTOM.map(item).join("")}
      <button class="nav-item" data-act="mode" title="Đổi sáng / tối">${icon(dark ? "moon" : "sun", dark ? "moon" : "sun")}<span class="nav-label">${dark ? "Nền tối" : "Nền sáng"}</span></button>
      ${S.app.native ? "" : `<button class="nav-item" data-act="quit" title="Thoát tool">${icon("power")}<span class="nav-label">Thoát tool</span></button>`}
      <button class="nav-item" data-act="sidebar" title="Thu gọn / mở rộng">${icon(open ? "chevrons-left" : "chevrons-right")}<span class="nav-label">Thu gọn</span></button>
    </nav>`;
}

/* ---------------- shared item pieces ---------------- */
function pills(it) {
  const [cls, ic, label] = WEB_STATUS[it.web_status] || WEB_STATUS.draft;
  return `<span class="pill ${it.has_listing ? "ok" : "warn"}">${icon(it.has_listing ? "check" : "pencil-line")}${it.has_listing ? "Đã có mô tả" : "Chưa có mô tả"}</span>
    <span class="pill ${cls}">${icon(ic)}${label}</span>`;
}
function itemSide(it) {
  const busy = S.busy[it.id];
  return `<div class="price" title="Giá bán (USD)"><span>$</span><input class="input" inputmode="decimal" value="${money(it.price)}" data-field="price" aria-label="Giá bán USD"></div>
    <button class="btn outline sm" data-act="write">${icon("sparkles")}${it.has_listing ? "Sửa mô tả" : "Viết mô tả"}</button>
    <button class="btn soft sm" data-act="publish" ${busy || S.running ? "disabled" : ""}>${icon(busy ? "loader-circle" : "cloud-upload", busy ? "spin" : "")}${busy ? "Đang đăng…" : it.web_status ? "Cập nhật" : "Đăng nháp"}</button>`;
}
function itemError(it) {
  return S.errors[it.id] ? `<div class="item-error">${esc(S.errors[it.id])}</div>` : "";
}
function header(ic, title, desc, extra = "") {
  return `<div class="page-header"><div class="icon-tile">${icon(ic)}</div><div class="grow"><h1>${title}</h1><p>${desc}</p></div>${extra}</div><div class="divider"></div>`;
}
function actionBar(kind) {
  const items = list(kind);
  const ready = items.filter((i) => i.has_listing && (kind === "pod" || i.has_cover)).length;
  return `<div class="action-bar">
    <button class="btn gradient xl grow" data-act="publish-all" data-kind="${kind}" ${!ready || S.running ? "disabled" : ""}>
      ${icon(S.running ? "loader-circle" : "cloud-upload", S.running ? "spin" : "")}${S.running ? "Đang đăng lên web…" : `Đăng ${ready} sản phẩm lên web (bản nháp)`}</button>
    <span class="muted small" style="max-width:220px">${ready}/${items.length} sản phẩm đã đủ mô tả${kind === "ebook" ? " và ảnh bìa" : ""}</span>
  </div>`;
}

/* ---------------- pages ---------------- */
const PAGES = {
  ebook() {
    const n = S.notes;
    const notes = !n ? "" : [
      n.no_cover?.length ? `<div class="note">${icon("image-off")}<span><b>${n.no_cover.length} PDF chưa có ảnh bìa cùng tên:</b> ${esc(n.no_cover.join(", "))}</span></div>` : "",
      n.no_pdf?.length ? `<div class="note info">${icon("info")}<span><b>${n.no_pdf.length} ảnh không có PDF cùng tên (bỏ qua):</b> ${esc(n.no_pdf.join(", "))}</span></div>` : "",
    ].join("");
    const rows = S.ebooks.map((it) => `<div class="item ${S.busy[it.id] ? "busy" : ""}" data-kind="ebook" data-id="${esc(it.id)}">
      <div class="thumb">${it.has_cover ? `<img alt="" src="/api/cover?k=${encodeURIComponent(window.SESSION_KEY)}&id=${encodeURIComponent(it.id)}">` : icon("image-off")}</div>
      <div class="item-main">
        <input class="input bare" value="${esc(it.title)}" data-field="title" aria-label="Tên sản phẩm" title="Bấm để sửa tên hiển thị trên web">
        <div class="item-meta"><span class="chip">${icon("file-text")}${esc(it.file)}</span>${it.pages ? `<span class="chip">${it.pages} trang</span>` : ""}${pills(it)}</div>
        ${itemError(it)}
      </div>
      <div class="item-side">${itemSide(it)}</div></div>`).join("");
    return `<div class="page">
      ${header("book-open", "Ebook", "PDF và ảnh bìa đặt cùng tên trong một thư mục. Tool viết mô tả, đặt giá, tải file lên web.")}
      <div class="top-block">
        <div class="row">
          <div class="input-icon">${icon("folder-open")}<input class="input" id="folder" value="${esc(S.config.ebook_folder)}" placeholder="Thư mục chứa PDF và ảnh bìa, ví dụ E:\\BOOK_1" aria-label="Thư mục ebook"></div>
          ${S.app.native ? `<button class="btn outline" style="height:44px" data-act="pick">${icon("folder-search")}Chọn thư mục</button>` : ""}
          <button class="btn soft" style="height:44px" data-act="scan">${icon("scan-search")}Quét</button>
        </div>${notes}
      </div>
      <div class="page-body">${rows || `<div class="empty"><div class="icon-tile">${icon("book-open")}</div><b>Chưa có ebook nào</b>
        <span>Chọn thư mục có file PDF và ảnh bìa trùng tên (ví dụ <code>Enoch.pdf</code> và <code>Enoch.png</code>) rồi bấm Quét.</span></div>`}</div>
      ${actionBar("ebook")}</div>`;
  },

  pod() {
    const errs = S.podErrors.map((e) => `<div class="note bad">${icon("circle-alert")}<span><b>${esc(e.url)}</b><br>${esc(e.error)}</span></div>`).join("");
    const rows = S.pods.map((it) => `<div class="item ${S.busy[it.id] ? "busy" : ""}" data-kind="pod" data-id="${esc(it.id)}">
      <div class="thumb square">${it.images?.[0] ? `<img alt="" src="${esc(it.images[0])}" referrerpolicy="no-referrer">` : icon("image-off")}</div>
      <div class="item-main">
        <input class="input bare" value="${esc(it.title)}" data-field="title" aria-label="Tên sản phẩm">
        <div class="item-meta">
          <select class="select" style="height:24px;font-size:12px" data-field="category" aria-label="Danh mục">${CATEGORIES.map((c) => `<option ${c === it.category ? "selected" : ""}>${c}</option>`).join("")}</select>
          <span class="chip">${icon("images")}${it.images?.length || 0} ảnh</span>${pills(it)}
        </div>${itemError(it)}
      </div>
      <div class="item-side">${itemSide(it)}
        <button class="btn ghost icon sm danger" data-act="remove" title="Bỏ khỏi danh sách" aria-label="Bỏ khỏi danh sách">${icon("trash-2")}</button></div></div>`).join("");
    return `<div class="page">
      ${header("shirt", "POD (Spring)", "Dán link sản phẩm trên Spring. Tool lấy tên, giá, ảnh rồi đăng lên web kèm nút mua dẫn về Spring.")}
      <div class="top-block">
        <div class="row" style="align-items:stretch">
          <textarea class="textarea grow" id="urls" rows="2" placeholder="Dán link Spring, mỗi link một dòng" aria-label="Link Spring"></textarea>
          <button class="btn soft" style="height:auto" data-act="pods-add" ${S.busy.pods ? "disabled" : ""}>${icon(S.busy.pods ? "loader-circle" : "link", S.busy.pods ? "spin" : "")}${S.busy.pods ? "Đang lấy…" : "Lấy thông tin"}</button>
        </div>${errs}
      </div>
      <div class="page-body">${rows || `<div class="empty"><div class="icon-tile">${icon("shirt")}</div><b>Chưa có sản phẩm POD</b>
        <span>Tạo sản phẩm trên Spring trước, rồi dán link của nó vào ô phía trên.</span></div>`}</div>
      ${actionBar("pod")}</div>`;
  },

  settings() {
    const p = S.ping;
    const conn = !p ? "" : p.error ? `<div class="note bad">${icon("circle-alert")}<span>${esc(p.error)}</span></div>`
      : `<div class="note ok">${icon("circle-check")}<span>Đã kết nối tới website <b>${esc(p.site || "")}</b>.</span></div>`;
    const u = S.update, d = S.upd;
    const pct = d?.total ? Math.round((d.got / d.total) * 100) : 0;
    const upd = !u ? "" : u.error ? `<div class="note bad">${icon("circle-alert")}<span>${esc(u.error)}</span></div>`
      : !u.newer ? `<div class="note ok">${icon("circle-check")}<span>Bạn đang dùng bản mới nhất (${esc(u.current)}).</span></div>`
      : `<div class="note info">${icon("gift")}<span><b>Có bản ${esc(u.latest)}.</b> ${esc((u.notes || "").slice(0, 400))}</span></div>
         ${d && d.state !== "idle" ? `<div class="progress"><i style="width:${d.state === "restarting" ? 100 : pct}%"></i></div>
           <span class="small muted">${d.state === "error" ? esc(d.error) : d.state === "restarting" ? "Đang cài và mở lại tool…" : `Đang tải ${pct}%`}</span>` : ""}
         <div class="row">${u.auto ? `<button class="btn soft" data-act="update-install" ${d?.state === "downloading" || d?.state === "restarting" ? "disabled" : ""}>${icon("download")}Cập nhật ngay</button>` : ""}
           <button class="btn outline" data-act="open" data-url="${esc(u.url)}">${icon("external-link")}Mở trang tải</button></div>`;
    return `<div class="page">
      ${header("settings", "Cài đặt", "Kết nối website, Lemon Squeezy, giao diện và cập nhật.")}
      <div class="page-body"><div class="sections">
        <section><div class="section-head"><div class="icon-tile sm">${icon("plug-zap")}</div><h2>Kết nối website</h2></div>
          <div class="card">
            <div class="set-row"><div class="grow"><b>Mã bí mật</b><span class="muted small">Website chỉ nhận sản phẩm từ tool có đúng mã này. Dán mã vào Base44 › Dashboard › Secrets với tên <code>TOOL_API_TOKEN</code>.</span></div>
              ${S.hasToken ? `<span class="pill ok">${icon("key-round")}Đã có mã</span><button class="btn outline sm" data-act="token-copy">${icon("copy")}Copy mã</button>`
                : `<button class="btn soft sm" data-act="token-new">${icon("key-round")}Tạo mã</button>`}
              <button class="btn ghost sm" data-act="token-paste">${icon("clipboard-paste")}Nhập mã có sẵn</button></div>
            <div class="card-div"></div>
            <div class="set-row"><div class="grow"><b>Kiểm tra</b><span class="muted small">Thử gọi website bằng mã hiện tại.</span></div>
              <button class="btn outline sm" data-act="ping" ${S.busy.ping ? "disabled" : ""}>${icon(S.busy.ping ? "loader-circle" : "refresh-cw", S.busy.ping ? "spin" : "")}Kiểm tra kết nối</button></div>
            ${conn}
          </div></section>
        <section><div class="section-head"><div class="icon-tile sm">${icon("citrus")}</div><h2>Lemon Squeezy và giá</h2></div>
          <div class="card">
            <div class="set-row"><div class="grow"><b>Variant ID dùng chung</b><span class="muted small">Một sản phẩm “Ebook” trên Lemon Squeezy dùng cho mọi ebook. Web tự đặt tên và giá từng cuốn lúc khách thanh toán.</span></div>
              <input class="input" style="width:150px" inputmode="numeric" value="${esc(S.config.shared_variant_id)}" data-config="shared_variant_id" placeholder="ví dụ 2204367" aria-label="Variant ID dùng chung"></div>
            <div class="card-div"></div>
            <div class="set-row"><div class="grow"><b>Giá mặc định</b><span class="muted small">Gán cho ebook mới quét. Sửa riêng từng cuốn ngay trên danh sách.</span></div>
              <div class="price"><span>$</span><input class="input" inputmode="decimal" value="${money(S.config.default_price)}" data-config="default_price" aria-label="Giá mặc định"></div></div>
          </div></section>
        <section><div class="section-head"><div class="icon-tile sm">${icon("palette")}</div><h2>Giao diện</h2></div>
          <div class="card"><div class="theme-grid">${Object.entries(THEMES).map(([id, t]) => `<button class="theme ${S.config.theme === id ? "active" : ""}" data-act="theme" data-theme="${id}">
            <i style="background:linear-gradient(135deg,hsl(${t.dark[1]}),hsl(${t.dark[0]}))"></i>${t.label}</button>`).join("")}</div></div></section>
        <section><div class="section-head"><div class="icon-tile sm">${icon("refresh-cw")}</div><h2>Cập nhật</h2></div>
          <div class="card">
            <div class="set-row"><div class="grow"><b>Phiên bản ${esc(S.app.version)}</b><span class="muted small">${esc(S.app.kind_text || "")}</span></div>
              <button class="btn outline sm" data-act="update-check" ${S.busy.update ? "disabled" : ""}>${icon(S.busy.update ? "loader-circle" : "refresh-cw", S.busy.update ? "spin" : "")}Kiểm tra cập nhật</button></div>
            ${upd}
          </div></section>
      </div></div></div>`;
  },

  guide() {
    const step = (t, d) => `<div class="step"><div><b>${t}</b><p>${d}</p></div></div>`;
    return `<div class="page">
      ${header("circle-help", "Hướng dẫn", "Làm một lần phần cài đặt, sau đó mỗi lô sản phẩm chỉ còn 3 bước.")}
      <div class="page-body"><div class="sections">
        <section><div class="section-head"><div class="icon-tile sm">${icon("wrench")}</div><h2>Cài đặt lần đầu</h2></div>
          <div class="card"><div class="steps">
            ${step("Tạo mã bí mật", "Vào Cài đặt › Tạo mã › Copy mã. Mở Base44 › Dashboard của web › Secrets, thêm secret tên <code>TOOL_API_TOKEN</code> và dán mã vào.")}
            ${step("Tạo một sản phẩm Ebook chung trên Lemon Squeezy", "Chỉ tạo một lần: tên bất kỳ (ví dụ “Dark Network Ebook”), giá bất kỳ, không cần đính kèm file. Copy Variant ID của nó, dán vào Cài đặt › Variant ID dùng chung.")}
            ${step("Kiểm tra kết nối", "Cài đặt › Kiểm tra kết nối phải báo xanh. Nếu báo chưa có cổng nhận sản phẩm thì website chưa được Publish bản mới.")}
          </div></div></section>
        <section><div class="section-head"><div class="icon-tile sm">${icon("book-open")}</div><h2>Đăng ebook</h2></div>
          <div class="card"><div class="steps">
            ${step("Quét thư mục", "Để PDF và ảnh bìa cùng tên trong một thư mục (<code>Ten-Sach.pdf</code> + <code>Ten-Sach.png</code>). Sửa tên hiển thị và giá ngay trên từng dòng.")}
            ${step("Viết mô tả", "Bấm Viết mô tả › Copy prompt › dán vào Claude hoặc ChatGPT › copy câu trả lời › dán lại vào tool › Lưu. Tool tự chuyển sang cuốn kế tiếp.")}
            ${step("Đăng lên web", "Bấm nút lớn phía dưới. Tool nén ảnh bìa, tải PDF lên kho riêng tư và tạo sản phẩm ở trạng thái <b>bản nháp</b>. Vào trang Admin của web xem lại rồi chuyển sang Published.")}
          </div></div></section>
        <section><div class="section-head"><div class="icon-tile sm">${icon("shirt")}</div><h2>Đăng sản phẩm POD</h2></div>
          <div class="card"><div class="steps">
            ${step("Dán link Spring", "Tạo sản phẩm trên Spring như bình thường, rồi dán link vào trang POD. Tool lấy tên, giá và ảnh.")}
            ${step("Viết mô tả và đăng", "Giống ebook. Nút mua trên web sẽ dẫn khách về trang Spring của sản phẩm.")}
          </div></div></section>
        <div class="note info">${icon("shield-check")}<span>Tool không bao giờ tự xuất bản hay xoá sản phẩm. Sản phẩm mới luôn là bản nháp; sản phẩm đã có trên web chỉ bị ghi đè khi bạn đồng ý.</span></div>
      </div></div></div>`;
  },
};

function render() {
  const body = $(".page-body");
  const scroll = body && render.page === S.page ? body.scrollTop : 0;   // a new page starts at the top
  render.page = S.page;
  const keep = {};
  for (const id of ["folder", "urls"]) if ($("#" + id)) keep[id] = $("#" + id).value;
  renderSidebar();
  $("#main").innerHTML = PAGES[S.page]();
  for (const [id, v] of Object.entries(keep)) if ($("#" + id)) $("#" + id).value = v;
  if ($(".page-body")) $(".page-body").scrollTop = scroll;
  lucide.createIcons();
}

/* ---------------- dialogs ---------------- */
function closeDialog() { $("#overlay").innerHTML = ""; }
function dialog(html, narrow = false) {
  $("#overlay").innerHTML = `<div class="overlay" data-act="overlay"><div class="dialog ${narrow ? "narrow" : ""}" role="dialog" aria-modal="true">${html}</div></div>`;
  lucide.createIcons();
}
function confirmDialog(title, text, okLabel) {
  return new Promise((resolve) => {
    dialog(`<div class="dialog-head"><div class="icon-tile sm">${icon("triangle-alert")}</div><h2>${esc(title)}</h2></div>
      <div class="dialog-body"><p>${esc(text)}</p></div>
      <div class="dialog-foot"><span class="grow"></span><button class="btn ghost" id="c-no">Thôi</button><button class="btn soft" id="c-yes">${esc(okLabel)}</button></div>`, true);
    $("#c-no").onclick = () => { closeDialog(); resolve(false); };
    $("#c-yes").onclick = () => { closeDialog(); resolve(true); };
  });
}

let writer = null;   // {kind, id, prompt}
async function openWriter(kind, id) {
  const it = find(kind, id);
  writer = { kind, id, prompt: "" };
  dialog(`<div class="dialog-head"><div class="icon-tile sm">${icon("sparkles")}</div><h2 class="grow">${esc(it.title)}</h2>
      <button class="btn ghost icon sm" data-act="close" aria-label="Đóng">${icon("x")}</button></div>
    <div class="dialog-body" id="w-body"><div class="row muted">${icon("loader-circle", "spin")}Đang đọc ${kind === "ebook" ? "PDF" : "sản phẩm"} và soạn prompt…</div></div>`);
  let data, saved;
  try {
    [data, saved] = await Promise.all([api("/api/item/prompt", { kind, id }), api("/api/item/listing", { kind, id })]);
  } catch (e) {
    if (writer?.id === id) $("#w-body").innerHTML = `<div class="note bad">${icon("circle-alert")}<span>${esc(e.message)}</span></div>`;
    lucide.createIcons();
    return;
  }
  if (!writer || writer.id !== id) return;
  writer.prompt = data.prompt;
  if (data.pages) it.pages = data.pages;
  const l = saved.listing;
  $("#w-body").innerHTML = `
    ${l ? `<div class="note ok">${icon("circle-check")}<span><b>Đã có mô tả:</b> ${esc(l.seo_title)}<br>${esc(l.meta_description)}</span></div>` : ""}
    <div class="card"><div class="steps">
      <div class="step"><div class="grow"><b>Copy prompt rồi dán vào Claude hoặc ChatGPT</b>
        <p>Prompt dài ${data.prompt.length.toLocaleString("vi-VN")} ký tự${kind === "ebook" && !data.attach ? ", đã kèm phần đầu và phần cuối sách" : ""}.</p>
        ${data.attach ? `<div class="note" style="margin-top:8px">${icon("paperclip")}<span>Nhớ đính kèm ${esc(data.attach)} vào tin nhắn.</span></div>` : ""}
        <div class="row wrap" style="margin-top:10px"><button class="btn soft" data-act="w-copy">${icon("copy")}Copy prompt</button>
          <button class="btn outline" data-act="open" data-url="https://claude.ai/new">${icon("external-link")}Mở Claude</button>
          <button class="btn outline" data-act="open" data-url="https://chatgpt.com/">${icon("external-link")}Mở ChatGPT</button></div></div></div>
      <div class="step"><div class="grow"><b>Dán câu trả lời vào đây</b>
        <p>Dán nguyên câu trả lời (khối JSON bắt đầu bằng <code>{</code>).</p>
        <textarea class="textarea mono" id="w-reply" rows="8" style="margin-top:8px" placeholder='{ "subtitle": "…", "description": "<p>…</p>", … }' aria-label="Câu trả lời của AI"></textarea>
        <div class="item-error" id="w-error"></div></div></div>
    </div></div>`;
  $(".dialog").insertAdjacentHTML("beforeend", `<div class="dialog-foot"><span class="muted small grow">Lưu xong tool tự mở sản phẩm kế tiếp chưa có mô tả.</span>
    <button class="btn ghost" data-act="close">Đóng</button><button class="btn gradient" data-act="w-save">${icon("check")}Lưu mô tả</button></div>`);
  lucide.createIcons();
}
async function saveWriter() {
  const { kind, id } = writer;
  try {
    const res = await api("/api/item/reply", { kind, id, text: $("#w-reply").value });
    Object.assign(find(kind, id), res.item);
    delete S.errors[id];
    const next = list(kind).find((i) => !i.has_listing);
    toast("success", next ? `Đã lưu mô tả. Tiếp theo: ${next.title}` : "Đã lưu mô tả. Tất cả sản phẩm đã có mô tả.");
    render();
    if (next) openWriter(kind, next.id); else closeDialog();
  } catch (e) {
    $("#w-error").textContent = e.message;
  }
}

/* ---------------- actions ---------------- */
async function publish(kind, id, { ask = true, overwrite = false } = {}) {
  S.busy[id] = true; delete S.errors[id]; render();
  try {
    const res = await api("/api/item/publish", { kind, id, overwrite });
    Object.assign(find(kind, id), res.item);
    return true;
  } catch (e) {
    if (e.code === "exists" && ask) {
      delete S.busy[id]; render();
      if (await confirmDialog("Trên web đã có sản phẩm này", `${e.message} Ghi đè nội dung trên web bằng nội dung trong tool? Trạng thái bán/nháp trên web giữ nguyên.`, "Ghi đè")) {
        return publish(kind, id, { ask: false, overwrite: true });
      }
      return false;
    }
    S.errors[id] = e.code === "exists" ? `${e.message} Bấm nút ở dòng này để chọn ghi đè.` : e.message;
    return false;
  } finally {
    delete S.busy[id]; render();
  }
}
async function publishAll(kind) {
  const todo = list(kind).filter((i) => i.has_listing && (kind === "pod" || i.has_cover));
  S.running = true; render();
  let ok = 0;
  for (const it of todo) if (await publish(kind, it.id, { ask: false })) ok += 1;
  S.running = false; render();
  toast(ok === todo.length ? "success" : "error", `Đã đăng ${ok}/${todo.length} sản phẩm lên web ở dạng bản nháp.${ok < todo.length ? " Xem lỗi ở từng dòng." : ""}`);
}
async function scan(folder) {
  try {
    const res = await api("/api/ebooks/scan", { folder });
    setState(res);
    if ($("#folder")) $("#folder").value = S.config.ebook_folder;
    S.notes = { no_cover: res.no_cover, no_pdf: res.no_pdf };
    toast("success", `Tìm thấy ${S.ebooks.length} ebook.`);
  } catch (e) { toast("error", e.message); }
  render();
}
async function pollUpdate() {
  try { S.upd = await api("/api/update/progress"); } catch (e) { return; }
  if (S.page === "settings") render();
  if (S.upd.state === "downloading") setTimeout(pollUpdate, 500);
}
async function checkUpdate(silent) {
  S.busy.update = true; if (!silent) render();
  try {
    S.update = await api("/api/update/check");
    if (silent && S.update.newer) toast("info", `Có bản ${S.update.latest}. Vào Cài đặt để cập nhật.`);
  } catch (e) { S.update = silent ? null : { error: e.message }; }
  delete S.busy.update; render();
}

const ACTIONS = {
  async mode() { setState(await api("/api/config", { mode: S.config.mode === "light" ? "dark" : "light" })); applyTheme(); render(); },
  async sidebar() { setState(await api("/api/config", { sidebar_open: S.config.sidebar_open === false })); render(); },
  async theme(el) { setState(await api("/api/config", { theme: el.dataset.theme })); applyTheme(); render(); },
  async quit() { await api("/api/quit").catch(() => {}); document.body.innerHTML = '<div class="empty" style="height:100%"><b>Tool đã thoát. Bạn có thể đóng tab này.</b></div>'; },
  async pick() { try { const r = await api("/api/pick-folder"); if (r.folder) { $("#folder").value = r.folder; scan(r.folder); } } catch (e) { toast("error", e.message); } },
  scan() { scan($("#folder").value); },
  write(el, row) { openWriter(row.dataset.kind, row.dataset.id); },
  publish(el, row) { publish(row.dataset.kind, row.dataset.id).then((ok) => ok && toast("success", "Đã đăng lên web ở dạng bản nháp.")); },
  "publish-all"(el) { publishAll(el.dataset.kind); },
  async remove(el, row) { await api("/api/item/remove", { kind: row.dataset.kind, id: row.dataset.id }); S.pods = S.pods.filter((i) => i.id !== row.dataset.id); render(); },
  async "pods-add"() {
    const urls = $("#urls").value;
    S.busy.pods = true; render();
    try {
      const res = await api("/api/pods/add", { urls });
      setState(res); S.podErrors = res.errors;
      if (res.added) toast("success", `Đã lấy ${res.added} sản phẩm từ Spring.`);
      $("#urls").value = res.errors.map((e) => e.url).join("\n");   // keep only the links that failed
    } catch (e) { toast("error", e.message); }
    delete S.busy.pods; render();
  },
  async "token-new"() { try { const r = await api("/api/token/generate"); S.hasToken = true; await copyText(r.token); toast("success", "Đã tạo mã và copy vào bộ nhớ tạm. Dán vào Base44 › Secrets › TOOL_API_TOKEN."); } catch (e) { toast("error", e.message); } render(); },
  async "token-copy"() { const r = await api("/api/token/show"); toast((await copyText(r.token)) ? "success" : "error", "Đã copy mã bí mật."); },
  "token-paste"() {
    dialog(`<div class="dialog-head"><div class="icon-tile sm">${icon("key-round")}</div><h2>Nhập mã có sẵn</h2></div>
      <div class="dialog-body"><p class="muted">Dùng khi cài tool trên máy thứ hai: dán đúng mã đang đặt trong Base44.</p>
        <input class="input" id="t-val" type="password" placeholder="Mã bí mật" aria-label="Mã bí mật"><div class="item-error" id="t-err"></div></div>
      <div class="dialog-foot"><span class="grow"></span><button class="btn ghost" data-act="close">Thôi</button><button class="btn soft" data-act="token-save">Lưu mã</button></div>`, true);
    $("#t-val").focus();
  },
  async "token-save"() { try { await api("/api/token/set", { token: $("#t-val").value }); S.hasToken = true; closeDialog(); toast("success", "Đã lưu mã."); render(); } catch (e) { $("#t-err").textContent = e.message; } },
  async ping() { S.busy.ping = true; render(); try { S.ping = await api("/api/site/ping"); } catch (e) { S.ping = { error: e.message }; } delete S.busy.ping; render(); },
  open(el) { api("/api/open", { url: el.dataset.url }).catch((e) => toast("error", e.message)); },
  "update-check"() { checkUpdate(false); },
  async "update-install"() { try { await api("/api/update/install"); pollUpdate(); } catch (e) { toast("error", e.message); } },
  close() { closeDialog(); writer = null; },
  overlay(el, row, ev) { if (ev.target === el && !$("#w-reply")?.value) { closeDialog(); writer = null; } },
  async "w-copy"() { toast((await copyText(writer.prompt)) ? "success" : "error", "Đã copy prompt. Dán vào Claude hoặc ChatGPT."); },
  "w-save"() { saveWriter(); },
};

document.addEventListener("click", (ev) => {
  const nav = ev.target.closest("[data-nav]");
  if (nav) { S.page = nav.dataset.nav; render(); return; }
  const el = ev.target.closest("[data-act]");
  if (el && !el.disabled && ACTIONS[el.dataset.act]) ACTIONS[el.dataset.act](el, el.closest(".item"), ev);
});
document.addEventListener("change", async (ev) => {
  const el = ev.target;
  try {
    if (el.dataset.config) { setState(await api("/api/config", { [el.dataset.config]: el.value })); toast("success", "Đã lưu."); render(); return; }
    const row = el.closest(".item");
    if (el.dataset.field && row) {
      const res = await api("/api/item/update", { kind: row.dataset.kind, id: row.dataset.id, [el.dataset.field]: el.value });
      Object.assign(find(row.dataset.kind, row.dataset.id), res.item);
      if (el.dataset.field === "price") el.value = money(res.item.price);
    }
  } catch (e) { toast("error", e.message); render(); }
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && $("#overlay").innerHTML && !$("#w-reply")?.value) { closeDialog(); writer = null; }
  if (ev.key === "Enter" && ev.target.matches("input[data-field], input[data-config]")) ev.target.blur();
  if (ev.key === "Enter" && ev.target.id === "folder") scan(ev.target.value);
});

(async function init() {
  try { setState(await api("/api/state")); } catch (e) { $("#main").innerHTML = `<div class="empty"><b>${esc(e.message)}</b></div>`; return; }
  applyTheme();
  render();
  checkUpdate(true);
})();
