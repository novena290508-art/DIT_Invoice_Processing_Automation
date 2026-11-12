(function () {
    "use strict";

    let statusChartInstance = null;
    let currencyChartInstance = null;

    function initSidebarToggle() {
        const sidebar = document.getElementById("sidebar");
        const toggleBtn = document.getElementById("sidebarToggle");
        if (!sidebar || !toggleBtn) return;

        toggleBtn.setAttribute("aria-expanded", "false");
        toggleBtn.addEventListener("click", function (event) {
            event.stopPropagation();
            const isOpen = sidebar.classList.toggle("is-open");
            toggleBtn.setAttribute("aria-expanded", String(isOpen));
        });

        document.addEventListener("click", function (event) {
            if (sidebar.classList.contains("is-open") && !sidebar.contains(event.target) && !toggleBtn.contains(event.target)) {
                sidebar.classList.remove("is-open");
                toggleBtn.setAttribute("aria-expanded", "false");
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && sidebar.classList.contains("is-open")) {
                sidebar.classList.remove("is-open");
                toggleBtn.setAttribute("aria-expanded", "false");
            }
        });
    }

    function renderChartFallback(canvas, message) {
        if (!canvas || !canvas.parentElement) return;
        const msgEl = document.createElement("p");
        msgEl.className = "chart-error-msg";
        msgEl.textContent = message;
        canvas.parentElement.replaceChild(msgEl, canvas);
    }

    function renderStatusChart(canvas, summary) {
        if (!canvas || typeof Chart === "undefined") return;
        if (statusChartInstance) {
            statusChartInstance.destroy();
            statusChartInstance = null;
        }
        const counts = [
            Number(summary.valid_invoices || 0),
            Number(summary.warning_invoices || 0),
            Number(summary.duplicate_invoices || 0),
            Number(summary.invalid_invoices || 0)
        ];
        const total = counts.reduce(function (acc, val) { return acc + val; }, 0);
        if (total === 0) {
            renderChartFallback(canvas, "No invoice status data available.");
            return;
        }
        statusChartInstance = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: ["Valid", "Warning", "Duplicate", "Invalid"],
                datasets: [{ data: counts, backgroundColor: ["#10b981", "#f59e0b", "#3b82f6", "#ef4444"], borderColor: "#0f1b38", borderWidth: 2 }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "bottom", labels: { color: "#cbd5e1", padding: 14 } } }
            }
        });
    }

    function renderCurrencyChart(canvas, summary) {
        if (!canvas || typeof Chart === "undefined") return;
        if (currencyChartInstance) {
            currencyChartInstance.destroy();
            currencyChartInstance = null;
        }
        const reconciliation = summary.currency_reconciliation || {};
        const currencies = Object.keys(reconciliation).sort();
        if (currencies.length === 0) {
            renderChartFallback(canvas, "No valid invoice currency totals available.");
            return;
        }
        const totals = currencies.map(function (curr) {
            return Number((reconciliation[curr] && reconciliation[curr].total_amount) || 0);
        });
        currencyChartInstance = new Chart(canvas, {
            type: "bar",
            data: {
                labels: currencies,
                datasets: [{ label: "Valid Total Amount (Per Currency)", data: totals, backgroundColor: ["#06b6d4", "#2563eb", "#22d3ee", "#60a5fa"], borderRadius: 6 }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: "#cbd5e1" } } },
                scales: {
                    x: { ticks: { color: "#cbd5e1" }, grid: { color: "rgba(148, 163, 184, 0.1)" } },
                    y: { beginAtZero: true, ticks: { color: "#cbd5e1" }, grid: { color: "rgba(148, 163, 184, 0.1)" } }
                }
            }
        });
    }

    function initDashboardCharts() {
        const container = document.getElementById("dashboardCharts");
        if (!container) return;
        const apiUrl = container.getAttribute("data-api-url");
        const statusCanvas = document.getElementById("statusDistributionChart");
        const currencyCanvas = document.getElementById("currencyTotalsChart");
        if (!apiUrl || !statusCanvas || !currencyCanvas) return;

        if (typeof Chart === "undefined") {
            renderChartFallback(statusCanvas, "Chart library unavailable.");
            renderChartFallback(currencyCanvas, "Chart library unavailable.");
            return;
        }

        fetch(apiUrl, { headers: { Accept: "application/json" } })
            .then(function (response) {
                if (!response.ok) throw new Error("HTTP " + response.status);
                return response.json();
            })
            .then(function (payload) {
                const summary = payload && payload.summary ? payload.summary : {};
                renderStatusChart(statusCanvas, summary);
                renderCurrencyChart(currencyCanvas, summary);
            })
            .catch(function () {
                renderChartFallback(statusCanvas, "Unable to load invoice status chart.");
                renderChartFallback(currencyCanvas, "Unable to load currency totals chart.");
            });
    }

    function initUploadForm() {
        const fileInput = document.getElementById("invoice_file");
        const uploadForm = document.querySelector(".upload-form");
        if (!fileInput || !uploadForm) return;

        const hintEl = uploadForm.querySelector(".file-hint");
        const submitBtn = uploadForm.querySelector('button[type="submit"]');
        const allowedExtensions = [".csv", ".xlsx"];

        function isValidExtension(filename) {
            const lower = filename.toLowerCase();
            return allowedExtensions.some(function (ext) { return lower.endsWith(ext); });
        }

        fileInput.addEventListener("change", function () {
            if (!fileInput.files || fileInput.files.length === 0) {
                if (hintEl) {
                    hintEl.textContent = "Maximum file size: 16 MB";
                    hintEl.classList.remove("is-error", "is-selected");
                }
                if (submitBtn) submitBtn.disabled = false;
                return;
            }
            const selectedFile = fileInput.files[0];
            if (!isValidExtension(selectedFile.name)) {
                if (hintEl) {
                    hintEl.textContent = "Unsupported file type: " + selectedFile.name + ". Please choose a .csv or .xlsx file.";
                    hintEl.classList.add("is-error");
                    hintEl.classList.remove("is-selected");
                }
                if (submitBtn) submitBtn.disabled = true;
                return;
            }
            if (hintEl) {
                const sizeKb = (selectedFile.size / 1024).toFixed(1);
                hintEl.textContent = "Selected: " + selectedFile.name + " (" + sizeKb + " KB)";
                hintEl.classList.add("is-selected");
                hintEl.classList.remove("is-error");
            }
            if (submitBtn) submitBtn.disabled = false;
        });

        uploadForm.addEventListener("submit", function (event) {
            if (!fileInput.files || fileInput.files.length === 0) {
                event.preventDefault();
                if (hintEl) {
                    hintEl.textContent = "Please select a .csv or .xlsx file before uploading.";
                    hintEl.classList.add("is-error");
                    hintEl.classList.remove("is-selected");
                }
                return;
            }
            if (!isValidExtension(fileInput.files[0].name)) {
                event.preventDefault();
                return;
            }
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Processing...";
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (document.body && document.body.dataset.ditInitialized === "true") return;
        if (document.body) document.body.dataset.ditInitialized = "true";
        initSidebarToggle();
        initDashboardCharts();
        initUploadForm();
    });
})();
