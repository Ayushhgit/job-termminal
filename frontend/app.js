/* ══════════════════════════════════════════════════════════════
   AI Job Intelligence — Dashboard App
   ══════════════════════════════════════════════════════════════ */

const API = "http://localhost:8000";

// ── State ─────────────────────────────────────────────────────
const state = {
    companies: { page: 1, pageSize: 50 },
    signals: { page: 1, pageSize: 50 },
    jobs: { page: 1, pageSize: 50 },
    alerts: { page: 1, pageSize: 50 },
    companyMap: {},
};

// ── DOM Helpers ───────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function showLoading() {
    $("#loadingOverlay").classList.add("active");
}
function hideLoading() {
    $("#loadingOverlay").classList.remove("active");
}

function showToast(msg, type = "info") {
    const container = $("#toastContainer");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function timeAgo(dateStr) {
    if (!dateStr) return "—";
    const d = new Date(dateStr);
    const now = new Date();
    const diff = Math.floor((now - d) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function probColor(p) {
    if (p >= 0.75) return "var(--accent-4)";
    if (p >= 0.5) return "var(--accent-5)";
    if (p >= 0.25) return "var(--accent-3)";
    return "var(--text-muted)";
}

function probBar(p) {
    const pct = Math.round((p || 0) * 100);
    return `
        <div class="prob-bar">
            <div class="prob-bar-track">
                <div class="prob-bar-fill" style="width:${pct}%;background:${probColor(p)}"></div>
            </div>
            <span class="prob-bar-value" style="color:${probColor(p)}">${pct}%</span>
        </div>`;
}

function tierBadge(tier) {
    return `<span class="badge badge-tier${tier}">Tier ${tier}</span>`;
}

function typeBadge(type) {
    return `<span class="badge badge-${type}">${type}</span>`;
}

// ── API Calls ─────────────────────────────────────────────────
async function api(path, opts = {}) {
    try {
        const res = await fetch(`${API}${path}`, opts);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (e) {
        console.error("API error:", e);
        showToast(`API error: ${e.message}`, "error");
        return null;
    }
}

// ── Health Check ──────────────────────────────────────────────
async function checkHealth() {
    const data = await api("/health");
    const dot = $("#apiStatus");
    const text = $("#apiStatusText");
    if (data && data.status === "ok") {
        dot.className = "status-dot online";
        text.textContent = "API Online";
    } else {
        dot.className = "status-dot offline";
        text.textContent = "API Offline";
    }
}

// ── Build Company Map ─────────────────────────────────────────
async function buildCompanyMap() {
    const data = await api("/companies?page_size=200");
    if (data && data.companies) {
        data.companies.forEach((c) => {
            state.companyMap[c.id] = c.company_name;
        });
    }
}

function companyName(id) {
    return state.companyMap[id] || `#${id}`;
}

// ── Overview ──────────────────────────────────────────────────
async function loadOverview() {
    const stats = await api("/stats");
    if (!stats) return;

    $("#statCompanies").textContent = stats.companies_total || 0;
    $("#statSignals").textContent = stats.signals_total || 0;
    $("#statJobs").textContent = stats.jobs_total || 0;
    $("#statHighProb").textContent = stats.high_probability_companies || 0;

    // Tier bars
    const tb = stats.tier_breakdown || {};
    const total = stats.companies_total || 1;
    const tierBarsEl = $("#tierBars");
    tierBarsEl.innerHTML = [
        { label: "Tier 1 — Top Companies", key: "tier_1", cls: "t1" },
        { label: "Tier 2 — Growth Stage", key: "tier_2", cls: "t2" },
        { label: "Tier 3 — Emerging", key: "tier_3", cls: "t3" },
    ]
        .map(
            (t) => `
        <div class="tier-row">
            <div class="tier-row-header">
                <span class="tier-row-label">${t.label}</span>
                <span class="tier-row-count">${tb[t.key] || 0}</span>
            </div>
            <div class="tier-bar">
                <div class="tier-bar-fill ${t.cls}" style="width:${((tb[t.key] || 0) / total) * 100}%"></div>
            </div>
        </div>`
        )
        .join("");

    // Top companies
    const top = await api("/companies?page_size=10");
    if (top && top.companies) {
        const tbody = $("#topCompaniesTable tbody");
        tbody.innerHTML = top.companies
            .map(
                (c, i) => `
            <tr>
                <td>${i + 1}</td>
                <td><strong>${c.company_name}</strong></td>
                <td>${tierBadge(c.tier)}</td>
                <td>${probBar(c.internship_probability)}</td>
                <td><button class="btn-scan" onclick="scanCompany(${c.id})">Scan</button></td>
            </tr>`
            )
            .join("");
    }

    // Latest signals
    const sigs = await api("/signals?page_size=8");
    if (sigs && sigs.signals) {
        const feed = $("#latestSignals");
        if (sigs.signals.length === 0) {
            feed.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📡</div><div class="empty-state-text">No signals yet. Run a scan to start collecting data!</div></div>`;
        } else {
            feed.innerHTML = sigs.signals
                .map(
                    (s) => `
                <div class="signal-item">
                    <div class="signal-dot ${s.signal_type}"></div>
                    <div class="signal-content">
                        <div class="signal-text">${escapeHtml(s.raw_data || "")}</div>
                        <div class="signal-meta">
                            ${typeBadge(s.signal_type)}
                            <span>${companyName(s.company_id)}</span>
                            <span>${s.internship_related ? "🎓 Internship" : ""}</span>
                            <span>${timeAgo(s.created_at)}</span>
                        </div>
                    </div>
                </div>`
                )
                .join("");
        }
    }
}

// ── Companies ─────────────────────────────────────────────────
async function loadCompanies() {
    const s = state.companies;
    const name = $("#companySearch").value;
    const tier = $("#tierFilter").value;
    const minProb = $("#minProbFilter").value;
    const country = $("#countryFilter").value;

    let q = `/companies?page=${s.page}&page_size=${s.pageSize}`;
    if (name) q += `&company_name=${encodeURIComponent(name)}`;
    if (tier) q += `&tier=${tier}`;
    if (minProb) q += `&min_probability=${minProb}`;
    if (country) q += `&country=${encodeURIComponent(country)}`;

    const data = await api(q);
    if (!data) return;

    const tbody = $("#companiesTable tbody");
    if (data.companies.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty-state"><div class="empty-state-icon">🏢</div><div class="empty-state-text">No companies found matching your filters.</div></td></tr>`;
    } else {
        tbody.innerHTML = data.companies
            .map(
                (c) => `
            <tr>
                <td>${c.id}</td>
                <td><strong>${c.company_name}</strong></td>
                <td><span class="badge badge-country-${(c.country || 'Global').toLowerCase()}">${c.country === 'India' ? '🇮🇳 India' : '🌍 Global'}</span></td>
                <td><a class="link" href="${c.website}" target="_blank">${new URL(c.website).hostname}</a></td>
                <td><a class="link" href="${c.careers_url}" target="_blank">Careers ↗</a></td>
                <td>${tierBadge(c.tier)}</td>
                <td>${probBar(c.internship_probability)}</td>
                <td><button class="btn-scan" onclick="scanCompany(${c.id})">🔍</button></td>
            </tr>`
            )
            .join("");
    }

    renderPagination("companiesPagination", data.total, s.page, s.pageSize, (p) => {
        s.page = p;
        loadCompanies();
    });
}

// ── Signals ───────────────────────────────────────────────────
async function loadSignals() {
    const s = state.signals;
    const type = $("#signalTypeFilter").value;
    const internOnly = $("#internshipOnlyFilter").checked;

    let q = `/signals?page=${s.page}&page_size=${s.pageSize}`;
    if (type) q += `&signal_type=${type}`;
    if (internOnly) q += `&internship_only=true`;

    const data = await api(q);
    if (!data) return;

    const tbody = $("#signalsTable tbody");
    if (data.signals.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state"><div class="empty-state-icon">📡</div><div class="empty-state-text">No signals found. Run a scan first!</div></td></tr>`;
    } else {
        tbody.innerHTML = data.signals
            .map(
                (s) => `
            <tr>
                <td>${s.id}</td>
                <td>${companyName(s.company_id)}</td>
                <td>${typeBadge(s.signal_type)}</td>
                <td title="${escapeHtml(s.raw_data || "")}">${escapeHtml((s.raw_data || "").slice(0, 80))}${(s.raw_data || "").length > 80 ? "…" : ""}</td>
                <td><span style="color:${probColor(s.confidence)}">${s.confidence}</span></td>
                <td><span class="badge ${s.internship_related ? "badge-yes" : "badge-no"}">${s.internship_related ? "Yes" : "No"}</span></td>
                <td>${timeAgo(s.created_at)}</td>
            </tr>`
            )
            .join("");
    }

    renderPagination("signalsPagination", data.total, s.page, s.pageSize, (p) => {
        s.page = p;
        loadSignals();
    });
}

// ── Jobs ──────────────────────────────────────────────────────
function jobTypeBadge(type) {
    const icons = { internship: '🎓', 'full-time': '💼', contract: '📝', 'part-time': '⏰' };
    return `<span class="badge badge-jobtype-${type || 'other'}">${icons[type] || '📄'} ${type || 'other'}</span>`;
}

async function loadJobs() {
    const s = state.jobs;
    const search = $("#jobSearch") ? $("#jobSearch").value : "";
    const jobType = $("#jobTypeFilter") ? $("#jobTypeFilter").value : "";
    const location = $("#jobLocationFilter") ? $("#jobLocationFilter").value : "";

    let q = `/jobs?page=${s.page}&page_size=${s.pageSize}`;
    if (search) q += `&search=${encodeURIComponent(search)}`;
    if (jobType) q += `&job_type=${encodeURIComponent(jobType)}`;
    if (location) q += `&location=${encodeURIComponent(location)}`;

    const data = await api(q);
    if (!data) return;

    const grid = $("#jobCardsGrid");
    if (data.jobs.length === 0) {
        grid.innerHTML = `<div class="empty-state"><div class="empty-state-icon">💼</div><div class="empty-state-text">No jobs found matching your filters. Try broadening your search!</div></div>`;
    } else {
        grid.innerHTML = data.jobs
            .map(
                (j) => `
            <div class="job-card">
                <div class="job-card-header">
                    <div class="job-card-company">${escapeHtml(j.company_name || 'Unknown')}</div>
                    ${jobTypeBadge(j.job_type)}
                </div>
                <h3 class="job-card-title">${escapeHtml(j.title)}</h3>
                <div class="job-card-meta">
                    ${j.location ? `<span class="job-meta-item">📍 ${escapeHtml(j.location)}</span>` : ''}
                    ${j.salary_range ? `<span class="job-meta-item">💰 ${escapeHtml(j.salary_range)}</span>` : ''}
                </div>
                <p class="job-card-desc">${escapeHtml((j.description || '').slice(0, 150))}${(j.description || '').length > 150 ? '…' : ''}</p>
                <div class="job-card-footer">
                    <span class="job-card-time">${timeAgo(j.detected_at)}</span>
                    <a class="btn btn-apply" href="${j.application_url || j.url || '#'}" target="_blank" rel="noopener">
                        Apply Now →
                    </a>
                </div>
            </div>`
            )
            .join("");
    }

    renderPagination("jobsPagination", data.total, s.page, s.pageSize, (p) => {
        s.page = p;
        loadJobs();
    });
}

// ── Alerts ────────────────────────────────────────────────────
async function loadAlerts() {
    const s = state.alerts;
    const data = await api(`/alerts?page=${s.page}&page_size=${s.pageSize}`);
    if (!data) return;

    const tbody = $("#alertsTable tbody");
    if (data.alerts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state"><div class="empty-state-icon">🔔</div><div class="empty-state-text">No alerts generated yet.</div></td></tr>`;
    } else {
        tbody.innerHTML = data.alerts
            .map(
                (a) => `
            <tr>
                <td>${a.id}</td>
                <td>${companyName(a.company_id)}</td>
                <td>${a.message}</td>
                <td>${probBar(a.probability)}</td>
                <td>${timeAgo(a.created_at)}</td>
            </tr>`
            )
            .join("");
    }

    renderPagination("alertsPagination", data.total, s.page, s.pageSize, (p) => {
        s.page = p;
        loadAlerts();
    });
}

// ── Scanner ───────────────────────────────────────────────────
async function scanNow() {
    const max = $("#scanMaxCompanies").value || 10;
    const btn = $("#scanNowBtn");
    const resultsEl = $("#batchScanResults");

    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">⏳</span> Scanning...';
    resultsEl.innerHTML = "";
    showLoading();

    const data = await api(`/scan/now?max_companies=${max}`, { method: "POST" });
    hideLoading();
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">⚡</span> Scan Now';

    if (!data) return;

    const st = data.signals_by_type || {};
    resultsEl.innerHTML = `
        <div class="scan-result-card">
            <h4>✅ Scan Complete</h4>
            <div class="scan-stat-row"><span class="scan-stat-label">Companies Scanned</span><span class="scan-stat-value">${data.companies_scanned}</span></div>
            <div class="scan-stat-row"><span class="scan-stat-label">Total Signals</span><span class="scan-stat-value">${data.signals_found}</span></div>
            <div class="scan-stat-row"><span class="scan-stat-label">Career Signals</span><span class="scan-stat-value">${st.career || 0}</span></div>
            <div class="scan-stat-row"><span class="scan-stat-label">GitHub Signals</span><span class="scan-stat-value">${st.github || 0}</span></div>
            <div class="scan-stat-row"><span class="scan-stat-label">Social Signals</span><span class="scan-stat-value">${st.social || 0}</span></div>
            <div class="scan-stat-row"><span class="scan-stat-label">Funding Signals</span><span class="scan-stat-value">${st.funding || 0}</span></div>
            <div class="scan-stat-row"><span class="scan-stat-label">Internship Signals</span><span class="scan-stat-value">${data.internship_signals || 0}</span></div>
        </div>`;

    showToast(`Scan complete — ${data.signals_found} signals found!`, "success");
    loadOverview();
}

async function scanCompany(id) {
    const resultsEl = $("#companyScanResults");
    showLoading();

    const data = await api(`/scan/company/${id}`, { method: "POST" });
    hideLoading();

    if (!data) return;

    // If on scanner page, show results there
    if (resultsEl) {
        const st = data.signals_by_type || {};
        resultsEl.innerHTML = `
            <div class="scan-result-card">
                <h4>✅ ${data.company || `Company #${id}`}</h4>
                <div class="scan-stat-row"><span class="scan-stat-label">Total Signals</span><span class="scan-stat-value">${data.signals_found}</span></div>
                <div class="scan-stat-row"><span class="scan-stat-label">Career</span><span class="scan-stat-value">${st.career || 0}</span></div>
                <div class="scan-stat-row"><span class="scan-stat-label">GitHub</span><span class="scan-stat-value">${st.github || 0}</span></div>
                <div class="scan-stat-row"><span class="scan-stat-label">Social</span><span class="scan-stat-value">${st.social || 0}</span></div>
                <div class="scan-stat-row"><span class="scan-stat-label">Probability</span><span class="scan-stat-value" style="color:${probColor(data.internship_probability)}">${Math.round((data.internship_probability || 0) * 100)}%</span></div>
            </div>`;
    }

    showToast(`Scanned ${data.company || id} — ${data.signals_found} signals`, "success");
}

// ── Pagination ────────────────────────────────────────────────
function renderPagination(containerId, total, page, pageSize, onPage) {
    const el = document.getElementById(containerId);
    const totalPages = Math.ceil(total / pageSize) || 1;

    let html = `<button class="page-btn" ${page <= 1 ? "disabled" : ""} onclick="void(0)">← Prev</button>`;
    html += `<span class="page-info">Page ${page} of ${totalPages} (${total} items)</span>`;
    html += `<button class="page-btn" ${page >= totalPages ? "disabled" : ""} onclick="void(0)">Next →</button>`;

    el.innerHTML = html;

    const btns = el.querySelectorAll(".page-btn");
    btns[0].addEventListener("click", () => { if (page > 1) onPage(page - 1); });
    btns[1].addEventListener("click", () => { if (page < totalPages) onPage(page + 1); });
}

// ── HTML Escape ───────────────────────────────────────────────
function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ── Navigation ────────────────────────────────────────────────
const sectionLoaders = {
    overview: loadOverview,
    companies: loadCompanies,
    signals: loadSignals,
    jobs: loadJobs,
    alerts: loadAlerts,
    scanner: () => {},
};

function navigateTo(section) {
    $$(".content-section").forEach((el) => el.classList.remove("active"));
    $(`#section-${section}`).classList.add("active");

    $$(".nav-item").forEach((el) => el.classList.remove("active"));
    $(`.nav-item[data-section="${section}"]`).classList.add("active");

    const titles = {
        overview: "Overview",
        companies: "Companies",
        signals: "Signals",
        jobs: "Jobs",
        alerts: "Alerts",
        scanner: "Scanner",
    };
    $("#pageTitle").textContent = titles[section] || section;

    if (sectionLoaders[section]) sectionLoaders[section]();

    // Close mobile sidebar
    $("#sidebar").classList.remove("open");
}

// ── Init ──────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
    // Nav
    $$(".nav-item").forEach((item) => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            navigateTo(item.dataset.section);
        });
    });

    // Mobile menu
    $("#menuToggle").addEventListener("click", () => {
        $("#sidebar").classList.toggle("open");
    });

    // Refresh
    $("#refreshBtn").addEventListener("click", () => {
        const active = $(".nav-item.active");
        if (active) navigateTo(active.dataset.section);
    });

    // Filters
    $("#filterCompaniesBtn").addEventListener("click", () => {
        state.companies.page = 1;
        loadCompanies();
    });

    $("#filterSignalsBtn").addEventListener("click", () => {
        state.signals.page = 1;
        loadSignals();
    });

    // Scanner
    $("#scanNowBtn").addEventListener("click", scanNow);
    $("#scanCompanyBtn").addEventListener("click", () => {
        const id = $("#scanCompanyId").value;
        if (id) scanCompany(id);
    });

    // Enter key on search
    $("#companySearch").addEventListener("keyup", (e) => {
        if (e.key === "Enter") {
            state.companies.page = 1;
            loadCompanies();
        }
    });

    // Job filters
    $("#filterJobsBtn").addEventListener("click", () => {
        state.jobs.page = 1;
        loadJobs();
    });

    $("#jobSearch").addEventListener("keyup", (e) => {
        if (e.key === "Enter") {
            state.jobs.page = 1;
            loadJobs();
        }
    });

    // Boot
    await checkHealth();
    await buildCompanyMap();
    await loadOverview();

    // Periodic health check
    setInterval(checkHealth, 30000);
});
