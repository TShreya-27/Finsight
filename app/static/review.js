const documentIdEl = document.querySelector("#document-id");
const statusText = document.querySelector("#status-text");
const anomalyCount = document.querySelector("#anomaly-count");
const workflowId = document.querySelector("#workflow-id");
const pdfFrame = document.querySelector("#pdf-frame");
const openPdfLink = document.querySelector("#open-pdf-link");
const anomalyList = document.querySelector("#anomaly-list");
const message = document.querySelector("#message");

const params = new URLSearchParams(window.location.search);
const documentId = params.get("document_id") || window.location.pathname.split("/").filter(Boolean).pop();
let currentWorkflowId = "";

async function readJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "non-JSON";
  const text = await response.text();
  if (!text) return {};

  try {
    return JSON.parse(text);
  } catch (error) {
    const path = new URL(response.url).pathname;
    throw new Error(`Expected JSON but got ${contentType} from ${path} (HTTP ${response.status}).`);
  }
}

function statusFromAction(action) {
  if (action === "correct") return "CORRECT";
  if (action === "incorrect") return "INCORRECT";
  return "MODIFIED";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatScore(score) {
  const numeric = Number(score || 0);
  return `${Math.round(numeric * 100)}%`;
}

async function applyDecision(anomalyId, action, notes) {
  const response = await fetch(`/api/v1/hitl/${anomalyId}/override`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workflow_id: currentWorkflowId,
      anomaly_id: anomalyId,
      action,
      notes,
    }),
  });

  if (!response.ok) {
    throw new Error("Could not update anomaly decision");
  }

  const badge = document.querySelector(`[data-status-for="${anomalyId}"]`);
  if (badge && !badge.classList.contains("verify-boxes")) {
    badge.textContent = statusFromAction(action);
  }
}

function renderAnomalies(anomalies) {
  anomalyList.innerHTML = "";
  if (!anomalies.length) {
    anomalyList.innerHTML = `
      <table class="human-table">
        <thead>
          <tr>
            <th>Sr No.</th>
            <th>Reason</th>
            <th>Verify</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td colspan="3">No anomaly lines were flagged.</td>
          </tr>
        </tbody>
      </table>
    `;
    return;
  }

  const rows = anomalies
    .map((anomaly, index) => {
      const reason = anomaly.reason || anomaly.description || "Detected by agent";
      const lineText = anomaly.line_text || anomaly.source_text || anomaly.metric_name;
      return `
        <tr>
          <td>${index + 1}</td>
          <td>
            <strong>${escapeHtml(reason)}</strong>
            <span>${escapeHtml(lineText)}</span>
            <small>Score ${formatScore(anomaly.score)} | ${escapeHtml(anomaly.severity)} | Page ${escapeHtml(anomaly.page || 1)}</small>
          </td>
          <td>
            <div class="verify-boxes" data-status-for="${anomaly.anomaly_id}">
              <button type="button" data-action="correct" data-id="${anomaly.anomaly_id}" aria-label="Mark anomaly ${index + 1} as correct">Yes</button>
              <button type="button" data-action="incorrect" data-id="${anomaly.anomaly_id}" aria-label="Mark anomaly ${index + 1} as incorrect">No</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");

  anomalyList.innerHTML = `
    <table class="human-table">
      <thead>
        <tr>
          <th>Sr No.</th>
          <th>Reason</th>
          <th>Verify</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

anomalyList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  button.disabled = true;
  try {
    await applyDecision(button.dataset.id, button.dataset.action, "Reviewed from Human Check table");
    const group = document.querySelector(`[data-status-for="${button.dataset.id}"]`);
    group?.querySelectorAll("button").forEach((item) => item.classList.remove("selected"));
    button.classList.add("selected");
    message.textContent = "Reviewer feedback saved.";
    message.classList.remove("error");
  } catch (error) {
    message.textContent = error.message;
    message.classList.add("error");
  } finally {
    button.disabled = false;
  }
});

async function loadReview() {
  documentIdEl.textContent = documentId;
  const statusResponse = await fetch(`/api/v1/documents/${documentId}/status`);
  const statusPayload = await readJsonResponse(statusResponse);
  if (!statusResponse.ok || statusPayload?.error) {
    throw new Error(statusPayload?.error?.message || "Document was not found.");
  }

  currentWorkflowId = statusPayload.workflow_id || "";
  statusText.textContent = statusPayload.status;
  anomalyCount.textContent = String(statusPayload.anomaly_count || 0);
  workflowId.textContent = currentWorkflowId || "Not started";

  const pdfUrl = statusPayload.highlighted_pdf_url || `/api/v1/documents/${documentId}/highlighted-pdf`;
  pdfFrame.src = `${pdfUrl}#view=FitH`;
  pdfFrame.parentElement?.classList.add("has-pdf");
  openPdfLink.href = pdfUrl;

  const anomalyResponse = await fetch(`/api/v1/documents/${documentId}/anomalies`);
  const anomalyPayload = await readJsonResponse(anomalyResponse);
  if (!anomalyResponse.ok || anomalyPayload?.error) {
    throw new Error(anomalyPayload?.error?.message || "Could not load anomalies.");
  }
  renderAnomalies(anomalyPayload.anomalies || []);

  message.textContent = statusPayload.anomaly_count
    ? "Review the highlighted PDF and resolve each flagged line."
    : "Analysis is complete. No anomalies were flagged.";
}

loadReview().catch((error) => {
  message.textContent = error.message;
  message.classList.add("error");
});
