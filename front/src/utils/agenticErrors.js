/**
 * User-facing copy and retry hints for agentic / broker failures (Task 3.4).
 */

export function normalizeAgentHttpError(status, rawMessage) {
  const msg = (rawMessage || "").trim();
  let display = msg;
  let retryable = false;

  const lower = msg.toLowerCase();

  if (/timed?\s*out|inactivity|workspace\s+closed/i.test(lower)) {
    return {
      display:
        "Agent session timed out after 30 minutes of inactivity",
      retryable: true,
      status: status === 504 ? 504 : status || 504,
    };
  }

  if (/slurm|batch\s*job|job\s*failed|drain.*fail/i.test(msg)) {
    const jobMatch = msg.match(/\b(\d{4,})\b/);
    const jobId = jobMatch ? jobMatch[1] : "unknown";
    return {
      display: `Workspace setup failed (Slurm job ${jobId} failed).`,
      retryable: true,
      status: status || 500,
    };
  }

  if (
    /container|workspace.*start|failed\s+to\s+start|image.*pull|apptainer|singularity/i.test(
      msg,
    )
  ) {
    const suffix = msg ? ` Error: ${msg}` : "";
    return {
      display: `Agent workspace failed to start.${suffix}`,
      retryable: true,
      status: status || 500,
    };
  }

  if (/session\s+ended|framework\s+crash|agent\s+crash|internal\s+error/i.test(lower)) {
    return {
      display: "Agent encountered error, session ended",
      retryable: true,
      status: status || 500,
    };
  }

  if (status === 401) {
    return {
      display: "Authentication required. Please log in again.",
      retryable: false,
      status: 401,
    };
  }

  if (status === 403) {
    return {
      display:
        "Access denied: you cannot access another user's workspace",
      retryable: false,
      status: 403,
    };
  }

  if (status === 503) {
    return {
      display:
        "Agent service temporarily unavailable. Please try again later.",
      retryable: true,
      status: 503,
    };
  }

  if (status === 504) {
    return {
      display:
        "Agent session timed out after 30 minutes of inactivity",
      retryable: true,
      status: 504,
    };
  }

  if (status >= 500) {
    retryable = true;
    display =
      msg ||
      "Something went wrong with the agent service. Please try again later.";
  } else if (status === 400 || status === 422) {
    display = msg || "The request could not be processed.";
    retryable = false;
  } else if (status > 0 && status < 500) {
    display = msg || "Request was not successful.";
    retryable = false;
  }

  if (status == null || status === 0) {
    return {
      display: msg || "Connection lost. Retrying failed — please try again.",
      retryable: true,
      status: 0,
    };
  }

  return { display, retryable, status };
}
