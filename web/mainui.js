/* ── State ── */
let currentTag = null;
let currentPage = 1;
let totalPages = 1;
let currentSort = "added";
let currentDuration = "";
let selectedVidAid = null;
let selectedVidBvid = null;
let allTags = [];

/* ── Init ── */
eel.expose(noop);
function noop() {}
window.addEventListener("load", async () => {
  try {
    const status = await eel.check_login_status()();
    if (status.logged_in) {
      showMainPage(status);
    } else {
      showLoginPage();
    }
  } catch (e) {
    showLoginPage();
  }
});

/* ── Login ── */
async function showLoginPage() {
  document.getElementById("login-page").classList.add("active");
  document.getElementById("main-page").classList.remove("active");
  refreshQR();
}

let qrPollTimer = null;

async function refreshQR() {
  const img = document.getElementById("qr-img");
  const expired = document.getElementById("qr-expired");
  const status = document.getElementById("qr-status");
  img.style.display = "none";
  expired.classList.remove("show");
  status.textContent = "正在生成二维码...";
  status.className = "status-text";

  if (qrPollTimer) clearInterval(qrPollTimer);
  await eel.cancel_qr()();

  const res = await eel.generate_qr()();
  if (!res.ok) {
    status.textContent = "生成失败: " + res.error;
    status.className = "status-text error";
    return;
  }
  img.src = res.qr_image;
  img.style.display = "block";
  status.textContent = "请使用B站客户端扫描二维码";
  status.className = "status-text";

  qrPollTimer = setInterval(async () => {
    const r = await eel.check_qr_state()();
    if (r.state === "scanned") {
      status.textContent = "已扫码，请在手机上确认...";
    } else if (r.state === "confirmed") {
      status.textContent = "已确认，正在登录...";
    } else if (r.state === "expired") {
      status.textContent = "二维码已过期";
      status.className = "status-text error";
      expired.classList.add("show");
      clearInterval(qrPollTimer);
    } else if (r.state === "done") {
      status.textContent = "登录成功！";
      status.className = "status-text done";
      clearInterval(qrPollTimer);
      setTimeout(
        () => showMainPage({ user_name: r.user_name, stats: r.stats }),
        800,
      );
    }
  }, 2000);
}

/* ── Main Page Transition ── */
let currentUser = "";

async function showMainPage(data) {
  document.getElementById("login-page").classList.remove("active");
  document.getElementById("main-page").classList.add("active");
  currentUser = data.user_name;
  document.getElementById("user-name-display").textContent =
    "👤 " + data.user_name;
  updateStats(data.stats);
  await loadTags();
  await loadVideos();
}

function updateStats(s) {
  document.getElementById("stat-total").textContent = s.total;
  document.getElementById("stat-watched").textContent = s.watched;
  document.getElementById("stat-tags").textContent = s.tags;
  document.getElementById("count-all").textContent = s.total;
}

/* ── Tags ── */
async function loadTags() {
  allTags = await eel.list_tags_gui()();
  const tagList = document.getElementById("tag-list");
  // Remove old tag items (keep first "全部")
  tagList
    .querySelectorAll(".tag-item:not(:first-child)")
    .forEach((el) => el.remove());

  allTags.forEach((t) => {
    const div = document.createElement("div");
    div.className = "tag-item";
    div.dataset.tag = t.name;
    div.innerHTML = `
      <span class="dot" style="background:${t.color}"></span>
      <span class="tag-name">${esc(t.name)}</span>
      <span class="count">${t.video_count}</span>
      <span class="del-tag" onclick="event.stopPropagation();deleteTag('${esc(t.name)}')">×</span>
    `;
    div.onclick = () => selectTag(div, t.name);
    tagList.appendChild(div);
  });
}

function selectTag(el, tagName) {
  document
    .querySelectorAll(".sidebar .tag-item")
    .forEach((i) => i.classList.remove("active"));
  el.classList.add("active");
  currentTag = tagName || null;
  currentPage = 1;
  document.getElementById("search-input").value = "";
  loadVideos();
}

async function createTag() {
  const nameInput = document.getElementById("new-tag-name");
  const colorInput = document.getElementById("new-tag-color");
  const name = nameInput.value.trim();
  if (!name) return;
  const res = await eel.add_tag_gui(name, colorInput.value)();
  if (res.ok) {
    nameInput.value = "";
    toast("标签已创建: " + name, "success");
    await loadTags();
    const s = await eel.get_stats()();
    updateStats(s);
  } else {
    toast(res.error || "创建失败", "error");
  }
}

async function deleteTag(name) {
  if (!confirm('删除标签 \"' + name + '\"？')) return;
  const res = await eel.remove_tag_gui(name)();
  if (res.ok) {
    toast("已删除标签: " + name, "success");
    await loadTags();
    await loadVideos();
  }
}

/* ── Videos ── */
async function loadVideos(append = false) {
  const grid = document.getElementById("video-grid");
  const empty = document.getElementById("empty-state");
  const loadMore = document.getElementById("load-more");

  if (!append) {
    grid.innerHTML = "";
    empty.style.display = "none";
    loadMore.style.display = "none";
  }

  const data = await eel.list_videos_gui(
    currentTag,
    currentPage,
    24,
    currentSort,
    currentDuration,
  )();
  totalPages = data.total_pages;
  document.getElementById("count-all").textContent = data.total;

  if (data.videos.length === 0 && !append) {
    empty.style.display = "flex";
    return;
  }

  data.videos.forEach((v) => renderCard(v, append));
  loadMore.style.display = currentPage < totalPages ? "flex" : "none";
}

function renderCard(v, append) {
  const grid = document.getElementById("video-grid");
  const card = document.createElement("div");
  card.className = "video-card";
  card.dataset.aid = v.aid;
  card.dataset.bvid = v.bvid;

  const tagsHtml = (v.tag_list || "")
    .split(", ")
    .filter(Boolean)
    .map((tn) => {
      const t = allTags.find((at) => at.name === tn);
      const color = t ? t.color : "#6c5ce7";
      return `<span class="chip" style="background:${color}">${esc(tn)}</span>`;
    })
    .join("");

  card.innerHTML = `
    <div class="cover">
      <img src="${esc(v.cover_url || "")}" loading="lazy" onerror="this.style.display='none'"
           referrerpolicy="no-referrer">
      <div class="duration">${v.duration_str}</div>
      <div class="actions-overlay">
        <button class="act-btn" title="观看" onclick="event.stopPropagation();doWatch('${v.bvid}')">▶</button>
        <button class="act-btn tag" title="标签" onclick="event.stopPropagation();openTagModal(${v.aid},'${v.bvid}','${esc(v.title).replace(/'/g, "\\'")}')">🏷</button>
        <button class="act-btn del" title="删除" onclick="event.stopPropagation();openDeleteModal(${v.aid},'${v.bvid}','${esc(v.title).replace(/'/g, "\\'")}')">🗑</button>
      </div>
    </div>
    <div class="info">
      <div class="title">${esc(v.title)}</div>
      <div class="author-row">
        <span class="author">${esc(v.author_name || "")}</span>
        <span class="added-date">${fmtDate(v.added_at)}</span>
      </div>
      <div class="tag-chips">${tagsHtml}</div>
      <div class="bvid">${v.bvid}</div>
    </div>
  `;
  card.onclick = () => doWatch(v.bvid);
  grid.appendChild(card);
}

function loadMore() {
  currentPage++;
  loadVideos(true);
}

/* ── Search ── */
let searchTimer = null;
document
  .getElementById("search-input")
  .addEventListener("input", async function () {
    clearTimeout(searchTimer);
    const q = this.value.trim();
    searchTimer = setTimeout(async () => {
      if (!q) {
        currentPage = 1;
        return loadVideos();
      }
      const data = await eel.search_videos_gui(q, currentDuration)();
      const grid = document.getElementById("video-grid");
      grid.innerHTML = "";
      const empty = document.getElementById("empty-state");
      const loadMore = document.getElementById("load-more");
      loadMore.style.display = "none";
      document.getElementById("count-all").textContent = data.total;
      if (data.videos.length === 0) {
        empty.style.display = "flex";
        empty.querySelector(".msg").textContent = "未找到匹配的视频";
        empty.querySelector(".sub").textContent = "试试其他关键词";
        return;
      }
      empty.style.display = "none";
      data.videos.forEach((v) => renderCard(v, false));
    }, 300);
  });

/* ── Sort ── */
document.getElementById("sort-select").addEventListener("change", function () {
  currentSort = this.value;
  currentPage = 1;
  loadVideos();
});

/* ── Duration Filter ── */
document.getElementById("duration-select").addEventListener("change", function () {
  currentDuration = this.value;
  currentPage = 1;
  loadVideos();
});

/* ── Sync ── */
async function doSync() {
  const btn = document.querySelector(".btn-sync");
  btn.innerHTML = "⏳ 同步中...";
  btn.disabled = true;
  try {
    const res = await eel.do_sync()();
    if (res.ok) {
      toast("同步完成，共 " + res.count + " 个视频", "success");
      updateStats(res.stats);
      currentPage = 1;
      await loadTags();
      await loadVideos();
    } else {
      toast(res.error || "同步失败", "error");
    }
  } catch (e) {
    toast("同步出错: " + e, "error");
  }
  btn.innerHTML = "🔄 同步";
  btn.disabled = false;
}

/* ── Watch ── */
async function doWatch(bvid) {
  await eel.watch_video(bvid)();
  // Show a small prompt-like behavior: after opening, ask about delete
  if (confirm("在浏览器中打开了视频。\n看完后是否从稍后再看中删除？")) {
    const res = await eel.delete_video(bvid)();
    if (res.ok) {
      toast("已删除", "success");
      removeCard(bvid);
      updateStats(res.stats);
      const s = await eel.get_stats()();
      document.getElementById("count-all").textContent = s.total;
    }
  }
}

/* ── Delete ── */
function openDeleteModal(aid, bvid, title) {
  selectedVidAid = aid;
  selectedVidBvid = bvid;
  document.getElementById("delete-modal-title").textContent =
    "从稍后再看删除: " + title + "？";
  document.getElementById("delete-modal").classList.add("show");
  document.getElementById("delete-confirm-btn").onclick = confirmDelete;
}

async function confirmDelete() {
  closeModal("delete-modal");
  const res = await eel.delete_video(selectedVidBvid)();
  if (res.ok) {
    toast("已删除", "success");
    removeCard(selectedVidBvid);
    updateStats(res.stats);
    const s = await eel.get_stats()();
    document.getElementById("count-all").textContent = s.total;
    await loadTags();
  } else {
    toast(res.error || "删除失败", "error");
  }
}

function removeCard(bvid) {
  const card = document.querySelector(`.video-card[data-bvid="${bvid}"]`);
  if (card) {
    card.style.transition = "opacity 0.3s, transform 0.3s";
    card.style.opacity = "0";
    card.style.transform = "scale(0.8)";
    setTimeout(() => card.remove(), 300);
  }
}

/* ── Tag Modal ── */
async function openTagModal(aid, bvid, title) {
  selectedVidAid = aid;
  selectedVidBvid = bvid;
  document.getElementById("tag-modal-title").textContent = title;
  const list = document.getElementById("tag-select-list");
  list.innerHTML = "";

  allTags = await eel.list_tags_gui()();
  const vtags = await eel.get_video_detail_gui(bvid)();
  const activeTagNames =
    vtags && vtags.tags ? vtags.tags.map((t) => t.name) : [];

  allTags.forEach((t) => {
    const span = document.createElement("span");
    span.className = "tag-opt" + (activeTagNames.includes(t.name) ? " on" : "");
    span.textContent = t.name;
    span.style.borderColor = t.color;
    span.onclick = async function () {
      if (this.classList.contains("on")) {
        const r = await eel.unassign_tag_gui(aid, t.name)();
        if (r.ok) {
          this.classList.remove("on");
          toast("已移除标签: " + t.name, "info");
        }
      } else {
        const r = await eel.assign_tag_gui(aid, t.name)();
        if (r.ok) {
          this.classList.add("on");
          toast("已打标签: " + t.name, "success");
        }
      }
      updateCardTags(bvid);
    };
    list.appendChild(span);
  });

  document.getElementById("tag-modal").classList.add("show");
}

async function updateCardTags(bvid) {
  const vt = await eel.get_video_detail_gui(bvid)();
  if (!vt) return;
  const card = document.querySelector(`.video-card[data-bvid="${bvid}"]`);
  if (!card) return;
  const chipsDiv = card.querySelector(".tag-chips");
  const tags = vt.tags || [];
  chipsDiv.innerHTML = tags
    .map((t) => {
      return `<span class="chip" style="background:${t.color}">${esc(t.name)}</span>`;
    })
    .join("");
  await loadTags();
}

/* ── Logout ── */
async function doLogout() {
  await eel.do_logout_gui()();
  currentPage = 1;
  showLoginPage();
}

/* ── Modal ── */
function closeModal(id) {
  document.getElementById(id).classList.remove("show");
}

/* ── Toast ── */
function toast(msg, type = "info") {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = "toast " + type;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => {
    el.style.animation = "fadeOut 0.3s ease-out forwards";
    setTimeout(() => el.remove(), 300);
  }, 3000);
}

/* ── Helpers ── */
function fmtDate(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.getFullYear() + "-" +
    String(d.getMonth() + 1).padStart(2, "0") + "-" +
    String(d.getDate()).padStart(2, "0");
}

function esc(s) {
  if (!s) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ── Keyboard ── */
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    document
      .querySelectorAll(".modal-overlay.show")
      .forEach((m) => m.classList.remove("show"));
  }
});
