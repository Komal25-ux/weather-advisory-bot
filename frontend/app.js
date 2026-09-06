/**
 * Weather Advisory Support Bot — Minimal Polished Frontend Logic
 * Strictly consumes backend API (/chat) and maintains session_id.
 * No client-side safety logic, weather calculations, or SOP thresholds.
 */

(() => {
  // DOM Elements
  const chatMessages = document.getElementById("chat-messages");
  const chatForm = document.getElementById("chat-form");
  const userInput = document.getElementById("user-input");
  const sendBtn = document.getElementById("send-btn");
  const newConvBtn = document.getElementById("new-conv-btn");
  const sessionIdDisplay = document.getElementById("session-id-display");
  const sessionStatusBadge = document.getElementById("session-status-badge");
  const loadingIndicator = document.getElementById("loading-indicator");
  const errorBanner = document.getElementById("error-banner");
  const errorMessage = document.getElementById("error-message");
  const errorDismiss = document.getElementById("error-dismiss");

  // State: Single session_id for the conversation lifetime
  let currentSessionId = "";

  /**
   * Generates a standard UUID v4 or fallback timestamp-based ID.
   */
  function generateSessionId() {
    if (window.crypto && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return "sess-" + Math.random().toString(36).substring(2, 11) + "-" + Date.now();
  }

  /**
   * Initializes or resets conversation session.
   */
  function initNewSession() {
    currentSessionId = generateSessionId();
    sessionIdDisplay.textContent = currentSessionId.substring(0, 8) + "...";
    sessionIdDisplay.title = currentSessionId;
    sessionStatusBadge.textContent = "New Session";
    sessionStatusBadge.style.backgroundColor = "rgba(59, 130, 246, 0.15)";
    sessionStatusBadge.style.color = "#60a5fa";

    // Reset chat messages to welcome message
    chatMessages.innerHTML = `
      <div class="message-group assistant-group">
        <div class="avatar assistant-avatar">🤖</div>
        <div class="message-content">
          <div class="message-bubble assistant-bubble">
            <p>Welcome! Ask me about planning any outdoor activity (e.g., <em>"Can I cycle in Berlin today?"</em> or <em>"Is it safe to take my toddler to the park in Paris?"</em>). I evaluate live weather conditions against strict, deterministic safety policies.</p>
          </div>
        </div>
      </div>
    `;

    hideError();
    userInput.value = "";
    userInput.focus();
  }

  /**
   * Shows error banner.
   */
  function showError(msg) {
    errorMessage.textContent = msg;
    errorBanner.classList.remove("hidden");
  }

  /**
   * Hides error banner.
   */
  function hideError() {
    errorBanner.classList.add("hidden");
  }

  /**
   * Toggles in-flight request UI state.
   */
  function setLoading(isLoading) {
    if (isLoading) {
      sendBtn.disabled = true;
      userInput.disabled = true;
      loadingIndicator.classList.remove("hidden");
      sessionStatusBadge.textContent = "Evaluating...";
      sessionStatusBadge.style.backgroundColor = "rgba(245, 158, 11, 0.15)";
      sessionStatusBadge.style.color = "#fbbf24";
    } else {
      sendBtn.disabled = false;
      userInput.disabled = false;
      loadingIndicator.classList.add("hidden");
      sessionStatusBadge.textContent = "Active";
      sessionStatusBadge.style.backgroundColor = "rgba(16, 185, 129, 0.15)";
      sessionStatusBadge.style.color = "#34d399";
      userInput.focus();
    }
  }

  /**
   * Appends a user message bubble.
   */
  function appendUserMessage(text) {
    const group = document.createElement("div");
    group.className = "message-group user-group";

    const avatar = document.createElement("div");
    avatar.className = "avatar user-avatar";
    avatar.textContent = "👤";

    const content = document.createElement("div");
    content.className = "message-content";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble user-bubble";
    bubble.textContent = text;

    content.appendChild(bubble);
    group.appendChild(avatar);
    group.appendChild(content);
    chatMessages.appendChild(group);

    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  /**
   * Formats markdown bolding/lists safely using DOM.
   */
  function renderFormattedText(text) {
    const container = document.createElement("div");
    const lines = text.split("\n");

    lines.forEach(line => {
      const trimmed = line.trim();
      if (!trimmed) return;

      if (trimmed.startsWith("- ")) {
        let ul = container.querySelector("ul:last-child");
        if (!ul) {
          ul = document.createElement("ul");
          container.appendChild(ul);
        }
        const li = document.createElement("li");
        li.innerHTML = escapeAndFormat(trimmed.substring(2));
        ul.appendChild(li);
      } else {
        const p = document.createElement("p");
        p.innerHTML = escapeAndFormat(trimmed);
        container.appendChild(p);
      }
    });

    return container;
  }

  function escapeAndFormat(str) {
    const div = document.createElement("div");
    div.textContent = str;
    let safe = div.innerHTML;
    // Format **bold**
    safe = safe.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // Format `code`
    safe = safe.replace(/`([^`]+)`/g, "<code>$1</code>");
    // Format *italics*
    safe = safe.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    return safe;
  }

  /**
   * Appends an assistant message with decision badges and details accordion.
   */
  function appendAssistantResponse(data) {
    const group = document.createElement("div");
    group.className = "message-group assistant-group";

    const avatar = document.createElement("div");
    avatar.className = "avatar assistant-avatar";
    avatar.textContent = "🤖";

    const content = document.createElement("div");
    content.className = "message-content";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble assistant-bubble";

    // 1. Badges Row (if decision exists)
    if (data.recommendation || data.severity || data.response_type !== "SUCCESS") {
      const badgeRow = document.createElement("div");
      badgeRow.className = "badge-row";

      if (data.recommendation) {
        const recBadge = document.createElement("span");
        const recLower = data.recommendation.toLowerCase().replace("_", "-");
        recBadge.className = `badge badge-${recLower}`;
        recBadge.textContent = data.recommendation.replace("_", " ");
        badgeRow.appendChild(recBadge);
      } else if (data.response_type === "NO_SOP") {
        const noSopBadge = document.createElement("span");
        noSopBadge.className = "badge badge-nosop";
        noSopBadge.textContent = "NO APPLICABLE POLICY";
        badgeRow.appendChild(noSopBadge);
      } else if (data.response_type === "INTENT_FAILURE") {
        const failBadge = document.createElement("span");
        failBadge.className = "badge badge-failure";
        failBadge.textContent = "SERVICE UNAVAILABLE";
        badgeRow.appendChild(failBadge);
      } else if (data.response_type === "WEATHER_FAILURE") {
        const failBadge = document.createElement("span");
        failBadge.className = "badge badge-failure";
        failBadge.textContent = "WEATHER RETRIEVAL FAILED";
        badgeRow.appendChild(failBadge);
      } else if (data.response_type === "LOCATION_FAILURE") {
        const failBadge = document.createElement("span");
        failBadge.className = "badge badge-failure";
        failBadge.textContent = "LOCATION RESOLUTION FAILED";
        badgeRow.appendChild(failBadge);
      } else if (data.response_type === "INTENT_CLARIFICATION") {
        const clarBadge = document.createElement("span");
        clarBadge.className = "badge badge-caution";
        clarBadge.textContent = "CLARIFICATION NEEDED";
        badgeRow.appendChild(clarBadge);
      }

      if (data.severity) {
        const sevBadge = document.createElement("span");
        sevBadge.className = "badge badge-severity";
        sevBadge.textContent = `SEVERITY: ${data.severity}`;
        badgeRow.appendChild(sevBadge);
      }

      bubble.appendChild(badgeRow);
    }

    // 2. Main Verbalized Response Text
    const textNode = renderFormattedText(data.response || "No response text.");
    bubble.appendChild(textNode);

    // 3. Compact "Decision Details / Why?" Section (if SOP was evaluated)
    if (data.sop_id || data.weather_facts || (data.applicable_sop_ids && data.applicable_sop_ids.length > 0)) {
      const details = document.createElement("details");
      details.className = "decision-details";

      const summary = document.createElement("summary");
      summary.className = "decision-summary";
      summary.innerHTML = `<span>🔍 Decision details ("Why?")</span> <span class="details-chevron">▾</span>`;
      details.appendChild(summary);

      const detailsBody = document.createElement("div");
      detailsBody.className = "decision-body";

      // Meta Table
      const table = document.createElement("table");
      table.className = "detail-table";
      table.innerHTML = `
        <tbody>
          ${data.recommendation ? `<tr><th>Recommendation</th><td>${escapeHtml(data.recommendation)}</td></tr>` : ""}
          ${data.severity ? `<tr><th>Severity Level</th><td>${escapeHtml(data.severity)}</td></tr>` : ""}
          ${data.location ? `<tr><th>Location</th><td>${escapeHtml(data.location)}</td></tr>` : ""}
          ${data.time_period ? `<tr><th>Time Period</th><td>${escapeHtml(data.time_period)}</td></tr>` : ""}
          ${data.sop_id ? `<tr><th>Selected Policy</th><td>${escapeHtml(data.sop_id)} (${escapeHtml(data.sop_name || "")})</td></tr>` : ""}
          ${data.applicable_sop_ids && data.applicable_sop_ids.length > 1 ? `<tr><th>Applicable SOPs</th><td>${escapeHtml(data.applicable_sop_ids.join(", "))}</td></tr>` : ""}
          ${data.decision_trace ? `<tr><th>Decision Trace</th><td>${escapeHtml(data.decision_trace)}</td></tr>` : ""}
        </tbody>
      `;
      detailsBody.appendChild(table);

      // Weather Facts Grid
      if (data.weather_facts) {
        const factsHeader = document.createElement("div");
        factsHeader.style.fontSize = "0.75rem";
        factsHeader.style.fontWeight = "700";
        factsHeader.style.color = "#94a3b8";
        factsHeader.style.marginTop = "6px";
        factsHeader.textContent = "WEATHER FACTS USED:";
        detailsBody.appendChild(factsHeader);

        const factsGrid = document.createElement("div");
        factsGrid.className = "facts-grid";

        const f = data.weather_facts;
        appendFact(factsGrid, "Wind Speed", f.wind_speed_kmh, "km/h");
        appendFact(factsGrid, "Wind Gusts", f.wind_gusts_kmh, "km/h");
        appendFact(factsGrid, "Temperature", f.temperature_c, "°C");
        appendFact(factsGrid, "Precipitation", f.precipitation_mm, "mm");
        appendFact(factsGrid, "Rain Prob", f.precipitation_probability, "%");
        appendFact(factsGrid, "UV Index", f.uv_index, "");
        appendFact(factsGrid, "Visibility", f.visibility_km, "km");

        detailsBody.appendChild(factsGrid);
      }

      details.appendChild(detailsBody);
      bubble.appendChild(details);
    }

    content.appendChild(bubble);
    group.appendChild(avatar);
    group.appendChild(content);
    chatMessages.appendChild(group);

    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function appendFact(grid, name, val, unit) {
    if (val === undefined || val === null) return;
    const item = document.createElement("div");
    item.className = "fact-item";
    item.innerHTML = `<div class="fact-name">${escapeHtml(name)}</div><div class="fact-value">${val} ${unit}</div>`;
    grid.appendChild(item);
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  /**
   * Submits user message to the backend /chat endpoint.
   */
  async function sendMessage() {
    const rawMessage = userInput.value;
    const message = rawMessage.trim();
    if (!message) return;

    hideError();
    appendUserMessage(message);
    userInput.value = "";
    setLoading(true);

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          session_id: currentSessionId,
          message: message
        })
      });

      if (!response.ok) {
        let errDetail = `Server returned status ${response.status}`;
        try {
          const errJson = await response.json();
          if (errJson.detail) {
            errDetail = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
          }
        } catch (_) {}
        throw new Error(errDetail);
      }

      const data = await response.json();
      appendAssistantResponse(data);

    } catch (err) {
      console.error("Chat API request error:", err);
      showError(`Request failed: ${err.message || "Network error. Please try again."}`);
      // Preserve the user message in view and allow retry
    } finally {
      setLoading(false);
    }
  }

  // Event Listeners
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage();
  });

  newConvBtn.addEventListener("click", () => {
    initNewSession();
  });

  errorDismiss.addEventListener("click", () => {
    hideError();
  });

  // Start initial session
  initNewSession();
})();
