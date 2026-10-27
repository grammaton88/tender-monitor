(() => {
  const stats = document.querySelector("#usage-stats");
  const refreshSource = document.querySelector("#dashboard-refresh-source");
  const updated = document.querySelector("#usage-updated");
  const sidebarUpdated = document.querySelector("#sidebar-usage-updated");
  const usageDate = document.querySelector("#usage-date");
  if (!refreshSource) return;

  const numberFormat = new Intl.NumberFormat("ka-GE");
  const dateFormat = new Intl.DateTimeFormat("ka-GE", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Tbilisi",
  });

  const formattedNow = () => dateFormat.format(new Date());
  const requestJson = async (url) => {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  };

  const setButtonBusy = (button, busy, busyLabel = "იტვირთება...") => {
    if (!button) return;
    if (busy) {
      button.dataset.originalText = button.textContent;
      button.textContent = busyLabel;
      button.disabled = true;
    } else {
      button.textContent = button.dataset.originalText || button.textContent;
      button.disabled = false;
    }
  };

  const setRefreshStatus = (selector, message) => {
    const element = document.querySelector(selector);
    if (element) element.textContent = message;
  };

  document.querySelectorAll(".run-created[datetime]").forEach((element) => {
    const date = new Date(element.dateTime);
    if (!Number.isNaN(date.getTime())) {
      element.textContent = new Intl.DateTimeFormat("ka-GE", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Tbilisi",
      }).format(date);
    }
  });

  const updateUsage = async (button = null) => {
    setButtonBusy(button, true);
    try {
      const data = await requestJson(refreshSource.dataset.usageUrl);
      if (usageDate && typeof data.date === "string") {
        usageDate.dateTime = data.date;
        usageDate.textContent = data.date;
      }
      for (const key of ["requests", "input", "output", "total", "quota_errors"]) {
        if (!Number.isSafeInteger(data[key])) continue;
        const formatted = numberFormat.format(data[key]);
        stats?.querySelector(`[data-metric="${key}"]`)?.replaceChildren(formatted);
        document.querySelectorAll(`[data-usage-metric="${key}"]`).forEach((value) => {
          value.textContent = formatted;
        });
      }
      if (data.updated_at) {
        const date = new Date(data.updated_at);
        const formatted = dateFormat.format(date);
        const label = `ბოლო მონაცემი: ${formatted}`;
        if (updated) updated.textContent = label;
        if (sidebarUpdated) sidebarUpdated.textContent = label;
      } else {
        if (updated) updated.textContent = "მონაცემები ჯერ არ განახლებულა";
        if (sidebarUpdated) sidebarUpdated.textContent = "მონაცემები ჯერ არ განახლებულა";
      }
      if (updated) {
        updated.dataset.status = "ok";
      }
      setRefreshStatus("#usage-refreshed", `განახლდა: ${formattedNow()}`);
    } catch {
      const message = "სტატისტიკის განახლება ვერ მოხერხდა";
      if (updated) {
        updated.textContent = `${message}; ნაჩვენებია ბოლო ჩატვირთული მონაცემები`;
        updated.dataset.status = "error";
      }
      if (sidebarUpdated) {
        sidebarUpdated.textContent = message;
        sidebarUpdated.dataset.status = "error";
      }
      setRefreshStatus("#usage-refreshed", message);
    } finally {
      setButtonBusy(button, false);
    }
  };

  const appendText = (parent, tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    parent.append(element);
    return element;
  };

  const runLabel = (run) => {
    if (run.conclusion === "success") return ["წარმატებული", "success"];
    if (run.conclusion) return ["წარუმატებელი", "failure"];
    if (run.status === "in_progress") return ["მიმდინარეობს", "running"];
    if (run.status === "queued") return ["რიგშია", "queued"];
    return [run.status, ""];
  };

  const renderRuns = (runs) => {
    const list = document.querySelector("#workflow-run-list");
    if (!list) return;
    list.replaceChildren();
    if (!runs.length) {
      appendText(list, "div", "runs-empty", "გაშვებები ჯერ არ არის");
      return;
    }
    for (const run of runs) {
      const card = appendText(list, "article", "run-card", "");
      card.dataset.runId = String(run.id ?? "");
      const main = appendText(card, "div", "run-card-main", "");
      const titleRow = appendText(main, "div", "run-title-row", "");
      appendText(titleRow, "h2", "", run.title || "IT Tender Monitor");
      const [statusText, statusClass] = runLabel(run);
      appendText(titleRow, "span", `run-badge ${statusClass}`, statusText);
      const eventLabel = run.event === "schedule"
        ? "ავტომატური"
        : run.event === "workflow_dispatch" ? "ხელით" : run.event;
      appendText(
        main,
        "p",
        "run-meta",
        [`გაშვება #${run.number}`, eventLabel, run.branch].filter(Boolean).join(" · "),
      );
      if (run.current_step) {
        appendText(main, "p", "run-current-step", `მიმდინარე ნაბიჯი: ${run.current_step}`);
      }
      const timeRow = appendText(main, "p", "run-time", "დაწყება: ");
      if (run.created_at) {
        const time = appendText(
          timeRow,
          "time",
          "run-created",
          new Date(run.created_at).toLocaleString("ka-GE", { timeZone: "Asia/Tbilisi" }),
        );
        time.dateTime = run.created_at;
      }
      const link = appendText(card, "a", "text-button run-log-link", "ჟურნალის ნახვა ↗");
      link.href = run.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
  };

  const updateRuns = async (button = null) => {
    const list = document.querySelector("#workflow-run-list");
    setButtonBusy(button, true);
    try {
      const data = await requestJson(refreshSource.dataset.runsUrl);
      renderRuns(data.runs || []);
      setRefreshStatus("#runs-refreshed", `განახლდა: ${formattedNow()}`);
      const active = (data.runs || []).some(
        (run) => run.status === "queued" || run.status === "in_progress",
      );
      document.querySelectorAll(".run-now-form button, .sidebar-run-form button").forEach((runButton) => {
        if (!runButton.dataset.originalRunLabel) {
          runButton.dataset.originalRunLabel = runButton.textContent;
        }
        runButton.disabled = active;
        runButton.title = active
          ? "მონიტორინგის გაშვება უკვე მიმდინარეობს ან რიგშია"
          : "";
        if (active) runButton.textContent = "მონიტორინგი მიმდინარეობს";
        else {
          runButton.textContent = runButton.dataset.originalRunLabel;
        }
      });
      if (list) list.dataset.refreshStatus = "ok";
    } catch {
      setRefreshStatus("#runs-refreshed", "გაშვების ისტორიის განახლება ვერ მოხერხდა");
      if (list) list.dataset.refreshStatus = "error";
    } finally {
      setButtonBusy(button, false);
    }
  };

  const updateHealth = async (button = null) => {
    const list = document.querySelector("#github-health-list");
    if (!list) return;
    setButtonBusy(button, true);
    try {
      const data = await requestJson(refreshSource.dataset.healthUrl);
      list.replaceChildren();
      for (const check of data.checks || []) {
        const item = appendText(list, "li", `health-item ${check.ok ? "healthy" : "unhealthy"}`, "");
        appendText(item, "strong", "", check.name);
        appendText(item, "span", "", check.detail);
      }
      setRefreshStatus("#health-refreshed", `შემოწმდა: ${formattedNow()}`);
    } catch {
      setRefreshStatus("#health-refreshed", "GitHub კავშირის შემოწმება ვერ მოხერხდა");
    } finally {
      setButtonBusy(button, false);
    }
  };

  document.querySelector("[data-refresh-usage]")?.addEventListener(
    "click",
    (event) => updateUsage(event.currentTarget),
  );
  document.querySelector("[data-refresh-runs]")?.addEventListener(
    "click",
    (event) => updateRuns(event.currentTarget),
  );
  document.querySelector("[data-refresh-health]")?.addEventListener(
    "click",
    (event) => updateHealth(event.currentTarget),
  );
  document.querySelectorAll(".run-now-form, .sidebar-run-form").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector("button");
      if (button) {
        button.dataset.originalRunLabel = button.textContent;
        button.textContent = "მოთხოვნა იგზავნება...";
        button.disabled = true;
      }
    });
  });

  if (stats || document.querySelector("[data-usage-metric]")) {
    updateUsage();
    window.setInterval(updateUsage, 60_000);
  }
  if (
    document.querySelector("#workflow-run-list") ||
    document.querySelector(".run-now-form button, .sidebar-run-form button")
  ) {
    updateRuns();
    window.setInterval(updateRuns, 30_000);
  }
})();

(() => {
  const toggle = document.querySelector("#menu-toggle");
  const sidebar = document.querySelector("#sidebar");
  const backdrop = document.querySelector("#sidebar-backdrop");
  if (!toggle || !sidebar) return;

  const setOpen = (open) => {
    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute("aria-label", open ? "მენიუს დახურვა" : "მენიუს გახსნა");
    if (backdrop) {
      if (open) backdrop.removeAttribute("hidden");
      else backdrop.setAttribute("hidden", "");
    }
  };

  toggle.addEventListener("click", () => {
    setOpen(!document.body.classList.contains("nav-open"));
  });

  if (backdrop) {
    backdrop.addEventListener("click", () => setOpen(false));
  }

  sidebar.querySelectorAll("a.nav-link, a.sidebar-usage-link").forEach((link) => {
    link.addEventListener("click", () => setOpen(false));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("nav-open")) {
      setOpen(false);
    }
  });
})();
